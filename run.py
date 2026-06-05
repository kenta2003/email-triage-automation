from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass

from config import ACCOUNTS, AccountConfig
from notifiers.slack import SlackNotifier
from processor import ClassifiedItem, classify_batch
from sources.gmail import GmailSource


@dataclass(frozen=True)
class ExecutionResult:
    account_name: str
    classified: list[ClassifiedItem]
    errors: list[str]


def _setup_logging() -> logging.Logger:
    os.makedirs("logs", exist_ok=True)

    logger = logging.getLogger("email-triage-automation")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s")

    fh = logging.FileHandler("logs/run.log", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)

    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _require_claude(logger: logging.Logger) -> bool:
    claude_bin = os.getenv("CLAUDE_BIN") or "claude"
    try:
        completed = subprocess.run(
            [claude_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode != 0:
            logger.error("Claude Code CLI not available: %s", completed.stderr.strip())
            return False
        return True
    except Exception as e:
        logger.error("Failed to verify Claude Code CLI: %s", e)
        return False


def _count_by_category(items: list[ClassifiedItem]) -> tuple[int, int, int]:
    reply_needed = sum(1 for i in items if i.category == "返信必要")
    should_read = sum(1 for i in items if i.category == "見るべき")
    skip = sum(1 for i in items if i.category == "スキップ")
    return reply_needed, should_read, skip


def _process_account(config: AccountConfig, logger: logging.Logger) -> ExecutionResult:
    errors: list[str] = []

    try:
        source = GmailSource(config)
        fetched = source.fetch()
        logger.info("[%s] fetched=%d", config.name, len(fetched))
    except Exception as e:
        msg = f"Gmail fetch failed: {e}"
        logger.error("[%s] %s", config.name, msg)
        return ExecutionResult(account_name=config.name, classified=[], errors=[msg])

    try:
        classified = classify_batch(fetched, config.rules)
        r, y, s = _count_by_category(classified)
        logger.info("[%s] classified: reply=%d read=%d skip=%d", config.name, r, y, s)
    except Exception as e:
        msg = f"classify failed: {e}"
        logger.error("[%s] %s", config.name, msg)
        classified = []
        errors.append(msg)

    try:
        if classified:
            source.mark_processed([c.source for c in classified])
            logger.info("[%s] marked processed=%d", config.name, len(classified))
    except Exception as e:
        msg = f"mark_processed failed: {e}"
        logger.error("[%s] %s", config.name, msg)
        errors.append(msg)

    try:
        notifier = SlackNotifier(config)
        notifier.notify(classified, account_name=config.name)
        logger.info("[%s] slack notified", config.name)
    except Exception as e:
        msg = f"slack notify failed: {e}"
        logger.error("[%s] %s", config.name, msg)
        errors.append(msg)

    return ExecutionResult(account_name=config.name, classified=classified, errors=errors)


def main() -> int:
    logger = _setup_logging()
    logger.info("run start")

    if not _require_claude(logger):
        logger.error("exit: Claude Code CLI is required")
        return 1

    results: list[ExecutionResult] = []
    for cfg in ACCOUNTS:
        try:
            results.append(_process_account(cfg, logger))
        except Exception as e:
            logger.exception("[%s] unexpected error: %s", cfg.name, e)
            results.append(ExecutionResult(account_name=cfg.name, classified=[], errors=[str(e)]))

    for r in results:
        reply_needed, should_read, skip = _count_by_category(r.classified)
        logger.info(
            "[%s] summary: reply=%d read=%d skip=%d errors=%d",
            r.account_name,
            reply_needed,
            should_read,
            skip,
            len(r.errors),
        )

    logger.info("run end")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
