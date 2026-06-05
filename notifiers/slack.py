from __future__ import annotations

from dataclasses import dataclass

import requests

from config import AccountConfig
from notifiers.base import BaseNotifier
from processor import ClassifiedItem


@dataclass(frozen=True)
class SlackMessage:
    text: str


class SlackNotifier(BaseNotifier):
    def __init__(self, config: AccountConfig) -> None:
        self._config = config

    def _post_webhook(self, webhook_url: str, text: str) -> None:
        resp = requests.post(webhook_url, json={"text": text}, timeout=10)
        if resp.status_code < 200 or resp.status_code >= 300:
            raise ValueError(f"Slack webhook failed (status={resp.status_code}): {resp.text}")

    def notify(self, items: list[ClassifiedItem], account_name: str) -> None:
        if not items:
            return

        reply_needed = [i for i in items if i.category == "返信必要"]
        should_read = [i for i in items if i.category == "見るべき"]
        skip = [i for i in items if i.category == "スキップ"]

        reply_webhook = self._config.reply_channel_webhook
        digest_webhook = self._config.digest_channel_webhook

        if reply_webhook:
            for i in reply_needed:
                msg = "\n".join(
                    [
                        f"[{account_name}] 🔴 【返信必要】",
                        f"From: {i.source.from_address}",
                        f"件名: {i.source.subject}",
                        f"受信: {i.source.received_at}",
                        "━━━━━━━━━━",
                        "【返信下書き】",
                        (i.draft_reply or "(下書き生成なし)"),
                    ]
                )
                self._post_webhook(reply_webhook, msg)

        if digest_webhook and (should_read or skip or reply_needed):
            lines: list[str] = []
            lines.append(f"[{account_name}] 🟡 【見るべきメール {len(should_read)}件】")
            for i in should_read:
                one_line = i.reasoning.replace("\n", " ").strip()
                lines.append(f"・{i.source.from_address} / {i.source.subject} — {one_line}")

            lines.append("")
            lines.append(f"⚪ 【スキップ {len(skip)}件】")
            for i in skip:
                lines.append(f"・{i.source.subject}（{i.source.from_address}）")

            lines.append("")
            lines.append(
                f"📊 返信必要: {len(reply_needed)}件 / 見るべき: {len(should_read)}件 / スキップ: {len(skip)}件"
            )

            self._post_webhook(digest_webhook, "\n".join(lines))
