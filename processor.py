from __future__ import annotations

import json
import re
import subprocess
import os
from dataclasses import dataclass
from typing import Literal

from config import ClassificationRules

Category = Literal["返信必要", "見るべき", "スキップ"]

_SKIP_PATTERNS = [
    r"メルマガ", r"ニュースレター", r"newsletter", r"unsubscribe",
    r"配信停止", r"一斉配信", r"キャンペーン", r"プロモーション",
    r"運営事務局", r"noreply@", r"no-reply@", r"donotreply@",
    r"マンスリーニュース", r"digest",
]
_REPLY_PATTERNS = [
    r"返信", r"至急", r"deadline", r"期限",
    r"面接", r"選考結果", r"内定", r"採用.*決定",
]


@dataclass(frozen=True)
class SourceItem:
    id: str
    from_address: str
    subject: str
    received_at: str
    body_preview: str
    account_name: str


@dataclass(frozen=True)
class ClassifiedItem:
    source: SourceItem
    category: Category
    draft_reply: str | None
    reasoning: str


def _build_prompt(items: list[SourceItem], rules: ClassificationRules) -> str:
    payload = [
        {
            "id": i.id,
            "from_address": i.from_address,
            "subject": i.subject,
            "received_at": i.received_at,
            "body_preview": i.body_preview,
            "account_name": i.account_name,
        }
        for i in items
    ]

    return "\n".join(
        [
            "以下のメールを指定ルールに従って分類し、JSON形式で返してください。",
            "",
            "## 分類ルール",
            f"- 返信必要: {rules.reply_needed}",
            f"- 見るべき: {rules.should_read}",
            f"- スキップ: {rules.skip}",
            "",
            "## 追加ルール（優先度高）",
            "- メルマガ・ニュースレター・プロモーション・一斉配信は必ず「スキップ」",
            "- noreply/no-reply アドレスからのメールで返信不要なものは「スキップ」",
            "- 自動配信サービスのメールは原則「スキップ」",
            "",
            "## 制約",
            "- 返信下書きは提案のみ。実際に送信しないこと",
            "- 「返信必要」以外のメールでは draft_reply を null にすること",
            "- 出力は必ず以下のJSON配列のみ。前後に説明文・マークダウン不可",
            "",
            "## 出力フォーマット",
            '[{"id":"...","category":"返信必要|見るべき|スキップ","draft_reply":"...|null","reasoning":"..."}]',
            "",
            "## 対象メール（JSON）",
            json.dumps(payload, ensure_ascii=False),
        ]
    )


def _extract_json(text: str) -> str:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"(\[[\s\S]*\])", text)
    if m:
        return m.group(1).strip()
    return text


def _run_claude(prompt: str, timeout_s: int) -> str:
    claude_bin = os.getenv("CLAUDE_BIN") or "claude"

    for args in [[claude_bin, "-p"]]:
        try:
            completed = subprocess.run(
                args,
                input=prompt.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_s,
                check=False,
            )
            stdout = completed.stdout.decode("utf-8", errors="replace").strip()
            stderr = completed.stderr.decode("utf-8", errors="replace").strip()

            if completed.returncode != 0:
                raise RuntimeError(
                    f"claude exit={completed.returncode}: {stderr[:300]}"
                )
            if not stdout:
                raise RuntimeError(f"claude returned empty stdout. stderr={stderr[:300]}")

            return _extract_json(stdout)
        except FileNotFoundError:
            raise RuntimeError(f"Claude CLI not found: {args[0]}")
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"claude timeout after {timeout_s}s")

    raise RuntimeError("claude CLI invocation failed")


def _parse_results(
    raw_json: str, items: list[SourceItem]
) -> list[tuple[str, Category, str | None, str]]:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse failed: {e}. raw={raw_json[:200]!r}") from e

    if not isinstance(data, list):
        raise ValueError("Claude output must be a JSON array")

    expected_ids = [i.id for i in items]
    results_by_id: dict[str, tuple[str, Category, str | None, str]] = {}

    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("Each result must be an object")
        id_ = entry.get("id")
        category = entry.get("category")
        draft_reply = entry.get("draft_reply")
        reasoning = entry.get("reasoning")

        if not isinstance(id_, str) or not id_:
            raise ValueError("Each result must include non-empty string 'id'")
        if category not in ("返信必要", "見るべき", "スキップ"):
            raise ValueError(f"Invalid category for id={id_}: {category!r}")
        if draft_reply is not None and not isinstance(draft_reply, str):
            raise ValueError(f"draft_reply must be string|null for id={id_}")
        if not isinstance(reasoning, str):
            raise ValueError(f"reasoning must be string for id={id_}")

        results_by_id[id_] = (id_, category, draft_reply, reasoning)

    missing = [id_ for id_ in expected_ids if id_ not in results_by_id]
    extra = [id_ for id_ in results_by_id.keys() if id_ not in set(expected_ids)]
    if missing or extra:
        raise ValueError(f"id mismatch: missing={missing}, extra={extra}")

    return [results_by_id[i] for i in expected_ids]


def _rule_based_classify(item: SourceItem) -> tuple[Category, str]:
    text = f"{item.from_address} {item.subject} {item.body_preview}".lower()

    for pat in _SKIP_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "スキップ", f"rule-based: matched skip pattern '{pat}'"

    for pat in _REPLY_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return "返信必要", f"rule-based: matched reply-needed pattern '{pat}'"

    return "見るべき", "rule-based: no clear pattern"


def classify_batch(items: list[SourceItem], rules: ClassificationRules) -> list[ClassifiedItem]:
    if len(items) > 50:
        raise ValueError("items must be <= 50")
    if not items:
        return []

    prompt = _build_prompt(items, rules)

    last_error: Exception | None = None
    for _attempt in range(3):
        try:
            raw = _run_claude(prompt, timeout_s=120)
            parsed = _parse_results(raw, items)
            by_id: dict[str, SourceItem] = {i.id: i for i in items}
            out: list[ClassifiedItem] = []
            for (id_, category, draft_reply, reasoning) in parsed:
                if category != "返信必要":
                    draft_reply = None
                out.append(
                    ClassifiedItem(
                        source=by_id[id_],
                        category=category,
                        draft_reply=draft_reply,
                        reasoning=reasoning,
                    )
                )
            return out
        except Exception as e:
            last_error = e

    fallback_prefix = f"claude failed({last_error}); rule-based fallback:"
    return [
        ClassifiedItem(
            source=i,
            category=(cat := _rule_based_classify(i)[0]),
            draft_reply=None,
            reasoning=f"{fallback_prefix} {_rule_based_classify(i)[1]}",
        )
        for i in items
    ]


if __name__ == "__main__":
    from config import ACCOUNTS

    sample = [
        SourceItem(
            id="sample-1",
            from_address="sender-a@example.com",
            subject="【要返信】ご確認のお願い",
            received_at="2026-01-01T10:00:00+09:00",
            body_preview="確認事項があります。返信お願いします。",
            account_name="Primary",
        ),
        SourceItem(
            id="sample-2",
            from_address="hr@example.com",
            subject="日程のご案内",
            received_at="2026-01-01T11:00:00+09:00",
            body_preview="候補日をお送りします。",
            account_name="Secondary",
        ),
        SourceItem(
            id="sample-3",
            from_address="newsletter@example.com",
            subject="今週のニュースレター",
            received_at="2026-01-01T12:00:00+09:00",
            body_preview="最新記事まとめです。",
            account_name="Secondary",
        ),
    ]

    results = classify_batch(sample, ACCOUNTS[1].rules)
    print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, default=str, indent=2))
