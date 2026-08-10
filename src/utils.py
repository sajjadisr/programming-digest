"""Shared paths, config loading, and small helpers used across the pipeline."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

SEEN_LINKS_PATH = DATA_DIR / "seen_links.json"
PICKS_LOG_PATH = DATA_DIR / "picks.jsonl"
PENDING_ITEMS_PATH = DATA_DIR / "pending_items.json"  # today's shortlist, keyed by short id
TELEGRAM_OFFSET_PATH = DATA_DIR / "telegram_update_offset.txt"
LAST_RUN_PATH = DATA_DIR / "last_run.txt"


def load_feeds_config() -> dict[str, Any]:
    with open(CONFIG_DIR / "feeds.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def register_guide() -> str:
    return load_text(CONFIG_DIR / "register.md")


def telegram_formatting_guide() -> str:
    return load_text(CONFIG_DIR / "telegram_formatting.md")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def env(name: str, default: str | None = None, required: bool = False) -> str | None:
    val = os.environ.get(name, default)
    if required and not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val
