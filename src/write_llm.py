"""Stage 3b: writing.

Per the plan (kept as-is) plus the review's addition:
  1. draft        - LLM writes the Persian item from full article text (or teaser fallback)
  2. regex pass    - cheap, deterministic: fix Arabic ي/ك -> Persian ی/ک, and flag
                      (not fix) formal/literary markers for the LLM pass to handle,
                      since "is this colloquial enough" is a judgment call
  3. register pass - LLM self-check against the register checklist, addresses
                      any regex-flagged formal markers
  4. fact pass     - LLM self-check: does every specific claim trace back to the
                      source text? This is new vs. the original plan, which only
                      had the source link as an after-the-fact safety net.

draft + register pass are "kept exactly as specified" from the plan's §4 item 4.
The fact pass is the review's addition, a genuinely separate failure mode from
register/style, so it's a separate call rather than folded into the same prompt.
"""
from __future__ import annotations

import re
from typing import Any

from llm_client import complete_json

# Arabic Yeh/Kaf -> Persian Yeh/Kaf. Deterministic, no judgment required.
_ARABIC_TO_PERSIAN_CHARS = {
    "\u064a": "\u06cc",  # ي -> ی
    "\u0643": "\u06a9",  # ك -> ک
}

# Formal/literary markers worth flagging for the register self-check pass.
# Not auto-fixed (rewriting around them requires judgment), just surfaced.
_FORMAL_MARKERS = [
    "می‌باشد", "میباشد", "گردید", "می‌گردد", "میگردد",
    "لازم به ذکر است", "در این راستا", "می بایست", "می‌بایست",
    "بدین ترتیب", "لذا",
]


def _fix_arabic_chars(text: str) -> str:
    for arabic, persian in _ARABIC_TO_PERSIAN_CHARS.items():
        text = text.replace(arabic, persian)
    return text


def _flag_formal_markers(text: str) -> list[str]:
    return [m for m in _FORMAL_MARKERS if m in text]


def _draft(item: dict[str, Any], article_text: str, is_full_article: bool,
           register_guide: str, taxonomy: list[str]) -> dict[str, str]:
    system = (
        "You write for a personal Telegram channel about programming, dev "
        "tooling, and AI coding tools. Follow the register guide exactly.\n\n"
        f"--- REGISTER GUIDE ---\n{register_guide}\n--- END REGISTER GUIDE ---\n\n"
        f"Relevant taxonomy tags available: {', '.join(taxonomy)}.\n\n"
        "Return ONLY valid JSON (no markdown fences): "
        '{"title_fa": "...", "body_fa": "...", "tags": ["..."]}. '
        "body_fa should be 3-5 sentences: what happened, why it matters to a "
        "developer, and what changed vs before, if relevant."
    )
    source_note = (
        "Full article text below." if is_full_article
        else "Only a short teaser was available (extraction failed) - write "
             "conservatively and don't invent specifics the teaser doesn't support."
    )
    user = (
        f"Title: {item['title']}\nSource: {item['source']}\nURL: {item['url']}\n\n"
        f"{source_note}\n\n{article_text}"
    )
    return complete_json(system, user, max_tokens=1024)


def _register_self_check(draft: dict[str, str], register_guide: str,
                          formal_flags: list[str]) -> dict[str, str]:
    if not formal_flags:
        return draft  # nothing flagged, skip the call entirely

    system = (
        "You are reviewing a Persian draft against a register checklist for a "
        "developer-focused Telegram channel. Revise ONLY where needed - don't "
        "rewrite lines that already fit.\n\n"
        f"--- REGISTER GUIDE ---\n{register_guide}\n--- END REGISTER GUIDE ---\n\n"
        "Return ONLY valid JSON: {\"title_fa\": \"...\", \"body_fa\": \"...\", \"tags\": [...]}"
    )
    user = (
        f"Draft title: {draft['title_fa']}\nDraft body: {draft['body_fa']}\n"
        f"Tags: {draft.get('tags', [])}\n\n"
        f"The automated check flagged these formal/literary phrases as present: "
        f"{', '.join(formal_flags)}. Rewrite around them in colloquial register "
        f"where they appear, per the guide. Keep everything else unless it "
        f"needs to change to keep the passage coherent."
    )
    return complete_json(system, user, max_tokens=1024)


def _fact_grounding_self_check(draft: dict[str, str], article_text: str,
                                is_full_article: bool) -> dict[str, Any]:
    system = (
        "You fact-check a Persian summary against its source text. This is "
        "purely about factual grounding, not style. For every specific claim "
        "in the summary (numbers, feature names, comparisons, causal claims), "
        "confirm it's actually supported by the source text below. If the "
        "source is only a short teaser, be strict: anything the teaser "
        "doesn't clearly support should be flagged.\n\n"
        "Return ONLY valid JSON: "
        '{"ok": true} if every claim is grounded, or '
        '{"ok": false, "issues": ["..."], "corrected_title_fa": "...", '
        '"corrected_body_fa": "..."} with the ungrounded claims removed or '
        "softened into what the source actually supports."
    )
    user = (
        f"Summary title: {draft['title_fa']}\nSummary body: {draft['body_fa']}\n\n"
        f"Source material ({'full article' if is_full_article else 'teaser only'}):\n"
        f"{article_text}"
    )
    # Checking several distinct claims against source text is a harder,
    # more multi-step task than drafting or the register pass - on Groq this
    # visibly needs more reasoning-token headroom before it gets to the JSON
    # answer (see llm_client.py's reasoning_effort comment). 1024 was too
    # tight even for the "ok": true happy path once a model actually had to
    # reason about it; 2560 leaves real room for the {"ok": false, "issues":
    # [...], "corrected_title_fa": ..., "corrected_body_fa": ...} case too.
    return complete_json(system, user, max_tokens=2560)


def write_item(item: dict[str, Any], article_text: str, is_full_article: bool,
               register_guide: str, taxonomy: list[str]) -> dict[str, Any]:
    """Runs the full draft -> regex -> register self-check -> fact self-check pipeline."""
    draft = _draft(item, article_text, is_full_article, register_guide, taxonomy)

    draft["title_fa"] = _fix_arabic_chars(draft["title_fa"])
    draft["body_fa"] = _fix_arabic_chars(draft["body_fa"])
    formal_flags = _flag_formal_markers(draft["title_fa"] + " " + draft["body_fa"])

    revised = _register_self_check(draft, register_guide, formal_flags)
    revised["title_fa"] = _fix_arabic_chars(revised["title_fa"])
    revised["body_fa"] = _fix_arabic_chars(revised["body_fa"])

    fact_check = _fact_grounding_self_check(revised, article_text, is_full_article)
    if not fact_check.get("ok", True):
        final_title = fact_check.get("corrected_title_fa") or revised["title_fa"]
        final_body = fact_check.get("corrected_body_fa") or revised["body_fa"]
        fact_issues = fact_check.get("issues", [])
    else:
        final_title, final_body = revised["title_fa"], revised["body_fa"]
        fact_issues = []

    return {
        **item,
        "title_fa": _fix_arabic_chars(final_title),
        "body_fa": _fix_arabic_chars(final_body),
        "tags": revised.get("tags", []),
        "register_flags_found": formal_flags,
        "fact_check_issues": fact_issues,
        "used_full_article": is_full_article,
    }
