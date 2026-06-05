from __future__ import annotations

import base64
import datetime as dt
import os
from email.utils import parsedate_to_datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import AccountConfig
from processor import SourceItem
from sources.base import BaseSource

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _load_creds(config: AccountConfig) -> Credentials:
    cred_path = config.credential_file
    token_path = config.token_file

    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"credential_file not found: {cred_path}")

    creds: Credentials | None = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES)
        creds = flow.run_local_server(port=0)

    _ensure_dir(token_path)
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    return creds


def _get_or_create_label(service, user_id: str, label_name: str) -> str:
    labels = service.users().labels().list(userId=user_id).execute().get("labels", [])
    for l in labels:
        if l.get("name") == label_name:
            return l["id"]

    created = (
        service.users()
        .labels()
        .create(
            userId=user_id,
            body={"name": label_name, "labelListVisibility": "labelShow", "messageListVisibility": "show"},
        )
        .execute()
    )
    return created["id"]


def _extract_body_preview(payload: dict) -> str:
    def walk(part: dict) -> list[dict]:
        out = [part]
        for c in part.get("parts", []) or []:
            out.extend(walk(c))
        return out

    parts = walk(payload)
    best = None
    for p in parts:
        mt = p.get("mimeType")
        body = p.get("body", {}) or {}
        data = body.get("data")
        if not data:
            continue
        if mt == "text/plain":
            best = data
            break
        if best is None and mt == "text/html":
            best = data

    if not best:
        return ""

    raw = base64.urlsafe_b64decode(best.encode("utf-8"))
    text = raw.decode("utf-8", errors="replace")
    return text[:500]


class GmailSource(BaseSource):
    def __init__(self, config: AccountConfig) -> None:
        self._config = config
        self._user_id = "me"
        self._service = None
        self._label_id_cache: str | None = None

    def _service_client(self):
        if self._service is None:
            creds = _load_creds(self._config)
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def fetch(self) -> list[SourceItem]:
        service = self._service_client()

        query = f'label:INBOX -label:"{self._config.processed_label}" newer_than:1d'

        resp = (
            service.users()
            .messages()
            .list(userId=self._user_id, q=query, maxResults=50)
            .execute()
        )
        messages = resp.get("messages", []) or []

        items: list[SourceItem] = []
        for m in messages:
            msg = (
                service.users()
                .messages()
                .get(userId=self._user_id, id=m["id"], format="full")
                .execute()
            )

            headers = {h["name"].lower(): h["value"] for h in (msg.get("payload", {}).get("headers", []) or [])}
            from_address = headers.get("from", "")
            subject = headers.get("subject", "")

            received_at = ""
            date_header = headers.get("date")
            if date_header:
                try:
                    received_at = parsedate_to_datetime(date_header).astimezone().isoformat()
                except Exception:
                    received_at = ""
            if not received_at:
                internal_ms = msg.get("internalDate")
                if internal_ms:
                    received_at = dt.datetime.fromtimestamp(int(internal_ms) / 1000, tz=dt.timezone.utc).isoformat()

            body_preview = _extract_body_preview(msg.get("payload", {}) or {})

            items.append(
                SourceItem(
                    id=msg["id"],
                    from_address=from_address,
                    subject=subject,
                    received_at=received_at,
                    body_preview=body_preview,
                    account_name=self._config.name,
                )
            )

        return items

    def mark_processed(self, items: list[SourceItem]) -> None:
        if not items:
            return

        service = self._service_client()
        if self._label_id_cache is None:
            self._label_id_cache = _get_or_create_label(service, self._user_id, self._config.processed_label)

        label_id = self._label_id_cache
        for i in items:
            (
                service.users()
                .messages()
                .modify(userId=self._user_id, id=i.id, body={"addLabelIds": [label_id], "removeLabelIds": []})
                .execute()
            )
