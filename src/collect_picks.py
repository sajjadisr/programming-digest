"""Entry point for the pick-collection run (.github/workflows/collect_picks.yml).

Polls Telegram once for any pick/reject button taps since the last run and
appends them to data/picks.jsonl. Cheap enough to run every 10-15 minutes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pick_logger import poll_and_log
from utils import env


def main() -> None:
    token = env("TELEGRAM_BOT_TOKEN", required=True)
    count = poll_and_log(token)
    print(f"[collect_picks] logged {count} new decision(s)")


if __name__ == "__main__":
    main()
