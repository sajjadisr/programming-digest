"""Stage 4: delivery.

Telegram DMs to the operator (not the channel - posting stays manual, outside
this pipeline, per "what happens to your pick": no changes there).

Changes from the base plan, per the review:
  - first message of the day notifies, the rest send silently, so an N-option
    day is one buzz on your phone, not N.
  - a short, silent "nothing cleared the bar today" message on a zero day, so
    "nothing qualified" and "something broke" don't look identical.
  - two buttons per item: pick, and "not for the channel" (a real reject
    signal for Phase 3 personalization, distinguishable from a non-tap).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!"


def escape_mdv2(text: str) -> str:
    return re.sub(f"([{re.escape(_MDV2_SPECIAL)}])", r"\\\1", text)


def _post(token: str, method: str, payload: dict) -> dict:
    resp = requests.post(TELEGRAM_API.format(token=token, method=method), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _date_header() -> str:
    # Persian-context channel, but keep this locale-agnostic/ISO to avoid
    # needing a Jalali calendar dependency; swap for a Jalali date if desired.
    today = datetime.now().strftime("%A, %Y-%m-%d")
    return f"📅 {escape_mdv2(today)}"


def _item_keyboard(item_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ انتخاب برای کانال", "callback_data": f"pick:{item_id}"},
                {"text": "❌ مناسب کانال نیست", "callback_data": f"reject:{item_id}"},
            ]
        ]
    }


def _format_item_message(item: dict[str, Any]) -> str:
    title = escape_mdv2(item["title_fa"])
    body = escape_mdv2(item["body_fa"])
    source_line = f"🔗 [منبع]({item['url']})"  # URL itself isn't escaped inside markdown link syntax
    tags = item.get("tags") or []
    tag_line = f"\n🏷 {escape_mdv2(' '.join(f'#{t}' for t in tags))}" if tags else ""
    return f"*{title}*\n\n{body}{tag_line}\n\n{source_line}"


def send_daily_options(token: str, chat_id: str, items: list[dict[str, Any]]) -> None:
    """Sends today's shortlist. Empty list -> a short silent zero-day ping."""
    if not items:
        _post(token, "sendMessage", {
            "chat_id": chat_id,
            "text": f"{_date_header()}\nامروز چیزی از فیلتر رد نشد\\.",
            "parse_mode": "MarkdownV2",
            "disable_notification": True,
        })
        return

    for i, item in enumerate(items):
        text = _format_item_message(item)
        if i == 0:
            text = f"{_date_header()}\n\n{text}"
        _post(token, "sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": False,
            "disable_notification": i != 0,  # only the first message buzzes
            "reply_markup": _item_keyboard(item["canonical_id"]),
        })
