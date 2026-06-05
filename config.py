from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class ClassificationRules:
    reply_needed: list[str]
    should_read: list[str]
    skip: list[str]


@dataclass(frozen=True)
class AccountConfig:
    name: str
    credential_file: str
    token_file: str
    processed_label: str
    reply_channel_webhook: str | None
    digest_channel_webhook: str | None
    rules: ClassificationRules


load_dotenv()


# Configure one entry per Gmail account you want to triage.
# Each account gets its own classification rules, Gmail label, and Slack channels.
ACCOUNTS: list[AccountConfig] = [
    AccountConfig(
        name="Primary",
        credential_file="credentials/primary_credentials.json",
        token_file="tokens/primary_token.json",
        processed_label="Claude-Processed-Primary",
        reply_channel_webhook=os.getenv("SLACK_PRIMARY_REPLY_WEBHOOK"),
        digest_channel_webhook=os.getenv("SLACK_PRIMARY_DIGEST_WEBHOOK"),
        rules=ClassificationRules(
            reply_needed=["返信", "ご確認", "依頼", "問い合わせ", "個別"],
            should_read=["お知らせ", "通知", "案内", "更新"],
            skip=["一斉配信", "広報", "メールマガジン", "自動送信"],
        ),
    ),
    AccountConfig(
        name="Secondary",
        credential_file="credentials/secondary_credentials.json",
        token_file="tokens/secondary_token.json",
        processed_label="Claude-Processed-Secondary",
        reply_channel_webhook=os.getenv("SLACK_SECONDARY_REPLY_WEBHOOK"),
        digest_channel_webhook=os.getenv("SLACK_SECONDARY_DIGEST_WEBHOOK"),
        rules=ClassificationRules(
            reply_needed=["ご連絡", "個別", "返信", "確認"],
            should_read=["案内", "日程", "結果", "通知"],
            skip=["メルマガ", "自動返信", "キャンペーン", "登録"],
        ),
    ),
]
