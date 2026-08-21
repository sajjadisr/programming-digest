"""Turns data/picks.jsonl into a compact block select_llm.py can inject into
its prompt, so the operator's pick/reject button taps actually change future
editorial judgment instead of just accumulating in a log file.

This was the one piece of "Phase 3 personalization" the README flagged as
not built yet: picks.jsonl already distinguished pick vs. reject vs.
untouched, but nothing read it back. This is the simplest version of that -
a few-shot calibration block, not a trained ranking model - which is enough
because the consumer is itself an LLM doing judgment calls (select_llm.py),
not a numeric scorer.

Deliberately NOT used for score.py's mechanical score: that stage is meant
to stay "cheap deterministic facts only" per its own docstring, and folding
soft per-source/per-tag accept rates in there would blur that line for
comparatively little benefit over just letting the select-stage LLM see the
raw examples and reason about them directly.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils import PICKS_LOG_PATH

# Keep both buckets small: this text is added to every select_llm.py call,
# and every token here counts against the same Groq per-minute budget the
# rest of that prompt is already tuned around (see select_llm.py's
# max_tokens comment). ~12 examples per bucket is enough for the LLM to spot
# a pattern (e.g. "rejects everything tagged ai_coding_tools from vendor X")
# without meaningfully growing the prompt.
MAX_EXAMPLES_PER_BUCKET = 12


def _read_all(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # a corrupt line shouldn't break the whole run
    return records


def _line(record: dict[str, Any]) -> str:
    title = (record.get("title") or "?").strip()[:90]
    source = record.get("source") or "?"
    tag = record.get("taxonomy_guess") or (record.get("tags") or ["?"])[0]
    return f"- [{source} / {tag}] {title}"


def build_feedback_block(limit_per_bucket: int = MAX_EXAMPLES_PER_BUCKET) -> str:
    """Returns "" if there's no pick/reject history yet (e.g. brand-new repo,
    or nobody has tapped a button yet) - select_and_cluster() handles that
    case as "no feedback section" rather than an empty/awkward block."""
    records = _read_all(PICKS_LOG_PATH)
    if not records:
        return ""

    picks = [r for r in records if r.get("action") == "pick"][-limit_per_bucket:]
    rejects = [r for r in records if r.get("action") == "reject"][-limit_per_bucket:]
    if not picks and not rejects:
        return ""

    parts = [
        "Recent human editorial decisions on past candidates from THIS "
        "channel (most recent last) - real signal for calibrating borderline "
        "judgment calls, not just examples:"
    ]
    if picks:
        parts.append("PICKED (kept for the channel):")
        parts.extend(_line(r) for r in picks)
    if rejects:
        parts.append("REJECTED (not for the channel):")
        parts.extend(_line(r) for r in rejects)
    return "\n".join(parts)
