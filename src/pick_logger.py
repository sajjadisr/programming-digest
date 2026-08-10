"""Stage 5: pick logging.

Polling, not webhook - nothing here is time-sensitive, so a GitHub Actions
cron job hitting getUpdates every ~15 minutes (see .github/workflows/
collect_picks.yml) is simpler than standing up a webhook receiver.

Logs both "pick" and "not for the channel" (reject) as distinguishable
outcomes, so a non-tap (still pending) isn't conflated with an active reject -
that distinction is what feeds the Phase 3 personalization pass.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from utils import (
    PENDING_ITEMS_PATH,
    PICKS_LOG_PATH,
    TELEGRAM_OFFSET_PATH,
    append_jsonl,
    load_json,
)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _post(token: str, method: str, payload: dict) -> dict:
    resp = requests.post(TELEGRAM_API.format(token=token, method=method), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _load_offset() -> int:
    if TELEGRAM_OFFSET_PATH.exists():
        return int(TELEGRAM_OFFSET_PATH.read_text().strip() or 0)
    return 0


def _save_offset(offset: int) -> None:
    TELEGRAM_OFFSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    TELEGRAM_OFFSET_PATH.write_text(str(offset))


def poll_and_log(token: str) -> int:
    """Polls getUpdates once, logs any pick/reject callbacks. Returns count logged."""
    offset = _load_offset()
    resp = _post(token, "getUpdates", {"offset": offset + 1, "timeout": 0})
    updates = resp.get("result", [])
    if not updates:
        return 0

    pending: dict[str, Any] = load_json(PENDING_ITEMS_PATH, {})
    logged = 0
    max_update_id = offset

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"])
        cq = update.get("callback_query")
        if not cq:
            continue

        data = cq.get("data", "")
        if ":" not in data:
            continue
        action, item_id = data.split(":", 1)
        if action not in ("pick", "reject"):
            continue

        item_meta = pending.get(item_id, {})
        append_jsonl(PICKS_LOG_PATH, {
            "item_id": item_id,
            "action": action,  # "pick" | "reject"
            "title": item_meta.get("title_fa") or item_meta.get("title"),
            "url": item_meta.get("url"),
            "tags": item_meta.get("tags"),
            "logged_at": datetime.now(tz=timezone.utc).isoformat(),
        })
        logged += 1

        # Ack the tap (removes the loading spinner) and drop the buttons so a
        # second tap can't double-log the same decision.
        _post(token, "answerCallbackQuery", {
            "callback_query_id": cq["id"],
            "text": "ثبت شد ✅" if action == "pick" else "ثبت شد ❌",
        })
        message = cq.get("message", {})
        if message.get("message_id") and message.get("chat", {}).get("id"):
            _post(token, "editMessageReplyMarkup", {
                "chat_id": message["chat"]["id"],
                "message_id": message["message_id"],
                "reply_markup": {"inline_keyboard": []},
            })

    _save_offset(max_update_id)
    return logged
