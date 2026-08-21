"""Stage 4: delivery.

Telegram DMs to the operator (not the channel - posting stays manual, outside
this pipeline, per "what happens to your pick": no changes there).

Changes from the base plan, per the review:
  - first message of the day notifies, the rest send silently, so an N-option
    day is one buzz on your phone, not N.
  - a short, silent "nothing cleared the bar today" message on a zero day, so
    "nothing qualified" and "something broke" don't look identical.
  - two buttons per item: pick, and "not for the channel" (a real reject
    signal, distinguishable from a non-tap - pick_logger.py logs both to
    data/picks.jsonl, which feedback.py then feeds back into select_llm.py's
    next run as calibration examples).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

_MDV2_SPECIAL = r"_*[]()~`>#+-=|{}.!"

# Max hashtags shown per item. Was unbounded (whatever write_llm.py's draft
# LLM returned, sometimes 3-4) - capped here too as a mechanical backstop on
# top of write_llm.py's own cap, consistent with this codebase's pattern of
# not trusting a single layer to enforce a hard limit.
_MAX_TAGS = 2

# Persian weekday names for the date header. The date itself stays Gregorian
# (developers here read release dates in Gregorian regardless of channel
# language), but the weekday NAME has no reason to be English on a Persian
# channel - %A gave "Thursday"/"Friday" etc. with no locale involved.
_WEEKDAYS_FA = {
    0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه",
    4: "جمعه", 5: "شنبه", 6: "یکشنبه",
}


def escape_mdv2(text: str) -> str:
    return re.sub(f"([{re.escape(_MDV2_SPECIAL)}])", r"\\\1", text)


def _post(token: str, method: str, payload: dict) -> dict:
    resp = requests.post(TELEGRAM_API.format(token=token, method=method), json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _date_header() -> str:
    # Persian-context channel, but keep the date itself locale-agnostic/ISO
    # to avoid needing a Jalali calendar dependency; swap for a Jalali date
    # if desired. The weekday name is translated (see _WEEKDAYS_FA above)
    # since there's no reason for that specific word to be English.
    now = datetime.now()
    weekday_fa = _WEEKDAYS_FA[now.weekday()]
    today = f"{weekday_fa}، {now.strftime('%Y-%m-%d')}"
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


def _format_item_message(item: dict[str, Any], tag_labels_fa: dict[str, str]) -> str:
    title = escape_mdv2(item["title_fa"])
    body = escape_mdv2(item["body_fa"])
    source_line = f"🔗 [منبع]({item['url']})"  # URL itself isn't escaped inside markdown link syntax
    # Always render through tag_labels_fa (config/feeds.yaml's taxonomy ->
    # label_fa map) rather than the raw English slug write_llm.py put in
    # "tags" - hashtags on a Persian channel should be Persian, and this way
    # that's guaranteed by code instead of depending on the writing LLM to
    # remember it every time. Capped to _MAX_TAGS as a second backstop on top
    # of write_llm.py's own cap.
    raw_tags = (item.get("tags") or [])[:_MAX_TAGS]
    tags_fa = [tag_labels_fa.get(t, t) for t in raw_tags]
    tag_line = f"\n🏷 {escape_mdv2(' '.join(f'#{t}' for t in tags_fa))}" if tags_fa else ""
    return f"*{title}*\n\n{body}{tag_line}\n\n{source_line}"


def send_daily_options(
    token: str,
    chat_id: str,
    items: list[dict[str, Any]],
    tag_labels_fa: dict[str, str] | None = None,
) -> None:
    """Sends today's shortlist. Empty list -> a short silent zero-day ping.

    tag_labels_fa: config/feeds.yaml's taxonomy key -> Persian label map
    (propose.py builds this from config["taxonomy"]). Defaults to {}, which
    falls back to showing the raw English slug - only happens if a caller
    doesn't pass it, propose.py always does.
    """
    tag_labels_fa = tag_labels_fa or {}
    if not items:
        _post(token, "sendMessage", {
            "chat_id": chat_id,
            "text": f"{_date_header()}\nامروز چیزی از فیلتر رد نشد\\.",
            "parse_mode": "MarkdownV2",
            "disable_notification": True,
        })
        return

    for i, item in enumerate(items):
        text = _format_item_message(item, tag_labels_fa)
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
