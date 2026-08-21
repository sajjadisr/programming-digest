"""Stage 3b: writing.

Per the plan (kept as-is) plus the review's addition, plus a broadened style
pass (see below):
  1. draft         - LLM writes the Persian item from full article text (or
                      teaser fallback), prompted with both the register guide
                      and the anti-AI-writing guide so most patterns never
                      make it into the first draft at all
  2. mechanical pass - cheap, deterministic character fixes: Arabic ي/ك ->
                      Persian ی/ک, curly quotes -> straight quotes. Also
                      flags (does not fix) formal/literary markers, Persian
                      AI-cliché phrases, and em/en dashes for the LLM pass to
                      handle, since rewriting around any of those requires
                      judgment about what to say instead
  3. style pass    - LLM self-check against BOTH the register checklist and
                      the anti-AI-writing guide, addresses whatever the
                      mechanical pass flagged. This replaces the original
                      register-only self-check: same trigger condition (skip
                      the call when nothing was flagged), broader scope.
  4. fact pass     - LLM self-check: does every specific claim trace back to the
                      source text? This is new vs. the original plan, which only
                      had the source link as an after-the-fact safety net.

draft + style pass are "kept exactly as specified" from the plan's §4 item 4,
just widened from register-only to register+anti-AI. The fact pass is the
review's addition, a genuinely separate failure mode from style, so it's a
separate call rather than folded into the same prompt.

Call count is unchanged from the original design (draft + optional style fix
+ fact-check = up to 3 calls) - see feeds.yaml's max_write_per_run comment on
why that matters: this pipeline runs on a free-tier daily quota.
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

# Curly quotes -> straight quotes. Also deterministic - a curly quote is a
# font/input-method artifact (it's literally what ChatGPT defaults to), not
# a judgment call about phrasing, so it's safe to swap unconditionally like
# the Arabic chars above. See persian_anti_ai_patterns.md #9.
_CURLY_TO_STRAIGHT_QUOTES = {
    "\u201c": '"',  # “
    "\u201d": '"',  # ”
    "\u2018": "'",  # ‘
    "\u2019": "'",  # ’
}

# Em dash, en dash, and spaced double-hyphens - Persian prose rarely uses
# these; when they show up it's almost always a leftover habit from the
# English source text. Flag-only, not auto-fixed: replacing one requires
# deciding whether the sentence wants a comma, a period, or a colon instead,
# which is exactly the kind of judgment call _dash_fallback deliberately
# does NOT try to make well - it's a last-resort net, not the primary fix.
_DASH_PATTERN = re.compile(r"\s+--\s+|—|–")

# Persian sentence boundaries, for the Latin-script-density check below. Only
# splits on a period when it's followed by whitespace and then a Persian
# letter - a bare "\." would also split inside Latin identifiers/URLs like
# "Bun.serve()" or "v2.1.224", which aren't sentence boundaries at all.
_PERSIAN_SENTENCE_SPLIT = re.compile(r"(?<=[؟!؛])\s+|(?<=\.)\s+(?=[\u0600-\u06FF])")

# A maximal run of Latin-script words - one technical term/identifier, OR
# several Latin words in a row separated only by whitespace with no Persian
# text between them (e.g. "Claude Code", "Vercel Functions", "Grok Build").
# The latter case matters: a two-word product name is ONE entity and one
# direction-switch for an RTL reader, not two - only a Persian word breaking
# up two Latin words is a separate switch. This is what's actually being
# counted below, not raw word count.
_LATIN_RUN = re.compile(
    r"[A-Za-z][A-Za-z0-9_.@/+#-]*(?:\(\))?(?:\s+[A-Za-z][A-Za-z0-9_.@/+#-]*(?:\(\))?)*"
)

# More than this many distinct Latin-script runs in a single sentence is what
# actually made the flagged example unreadable ("Bun runtime تو Vercel
# Functions حالا می‌تونه Bun.serve() رو به‌عنوان ورودی‌کد بپذیره" has 3: "Bun
# runtime", "Vercel Functions", "Bun.serve()") - the RTL/LTR direction
# switches back and forth once per run, which is what's fatiguing to read,
# not any single English word on its own. See persian_anti_ai_patterns.md's
# new section on this for the fix the style pass should apply.
_MAX_LATIN_CHUNKS_PER_SENTENCE = 2

# Hard cap on how many hashtags an item ships with, enforced here as well as
# in deliver.py (which also translates them to Persian) - two independent
# backstops on the same limit, consistent with this file's general "flag/cap
# mechanically, don't just hope the prompt is followed" approach.
_MAX_TAGS = 2

# Formal/literary markers worth flagging for the style self-check pass.
# Not auto-fixed (rewriting around them requires judgment), just surfaced.
_FORMAL_MARKERS = [
    "می‌باشد", "میباشد", "گردید", "می‌گردد", "میگردد",
    "لازم به ذکر است", "در این راستا", "می بایست", "می‌بایست",
    "بدین ترتیب", "لذا",
]

# Persian AI-cliché vocabulary - the Persian-language equivalent of
# Wikipedia's "AI vocabulary" list (see persian_anti_ai_patterns.md #2).
# Distinct failure mode from _FORMAL_MARKERS: those are about literary vs.
# colloquial *register*, these are stock hype/filler phrases that read as
# AI-written even in perfectly colloquial Persian. Flag-only for the same
# reason as the formal markers - fixing these needs a real replacement
# clause, not a mechanical swap.
_AI_CLICHE_PHRASES = [
    "نقش بسزایی", "نقش مهمی ایفا", "نقش کلیدی ایفا", "در دنیای امروز",
    "گامی مهم در راستای", "گام بزرگی در مسیر", "بدون شک", "شکی نیست که",
    "تجربه‌ای بی‌نظیر", "تجربه‌ای منحصربه‌فرد", "متحول خواهد کرد",
    "متحول می‌کند", "پتانسیل بالایی", "چشم‌انداز روشنی", "آینده‌ی روشنی",
    "باید منتظر ماند و دید", "نویدبخش", "سنگ بنای", "نقطه عطف",
]


def _fix_arabic_chars(text: str) -> str:
    for arabic, persian in _ARABIC_TO_PERSIAN_CHARS.items():
        text = text.replace(arabic, persian)
    return text


def _fix_curly_quotes(text: str) -> str:
    for curly, straight in _CURLY_TO_STRAIGHT_QUOTES.items():
        text = text.replace(curly, straight)
    return text


def _mechanical_fixes(text: str) -> str:
    """Zero-judgment character-level fixes - safe to apply unconditionally,
    any number of times (idempotent), unlike the flag-only checks below."""
    return _fix_curly_quotes(_fix_arabic_chars(text))


def _dash_fallback(text: str) -> str:
    """Last-resort cleanup if a dash survives the style self-check pass. A
    blunt comma swap reads worse than a properly restructured sentence, but
    it reads better than shipping one of the most recognizable AI tells
    there is - this only runs when the LLM pass, despite being told about
    the flagged dash, didn't remove it."""
    text = _DASH_PATTERN.sub("،", text)
    text = re.sub(r"\s+،", "،", text)   # no space before a Persian comma
    text = re.sub(r"،(?!\s)", "، ", text)  # ensure a space after it
    return text


def _flag_dense_latin_runs(text: str) -> list[str]:
    """Flags any sentence packing more than _MAX_LATIN_CHUNKS_PER_SENTENCE
    separate Latin-script runs into it - the RTL-readability failure mode
    where several English words/identifiers are scattered through one
    Persian sentence with only a word or two of Persian between them each
    time. A multi-word product name ("Vercel Functions") counts as ONE run,
    not one per word - see _LATIN_RUN above. Returns one flag string per
    offending sentence (with the sentence itself included) so the style pass
    has the actual text to restructure, not just a category name."""
    flags = []
    for sentence in _PERSIAN_SENTENCE_SPLIT.split(text):
        chunks = _LATIN_RUN.findall(sentence)
        if len(chunks) > _MAX_LATIN_CHUNKS_PER_SENTENCE:
            flags.append(
                f"English-term density ({len(chunks)} separate Latin-script "
                f"terms in one sentence - restructure so at most "
                f"{_MAX_LATIN_CHUNKS_PER_SENTENCE} appear per sentence; see "
                f"persian_anti_ai_patterns.md's density section): "
                f"{sentence.strip()[:120]}"
            )
    return flags


def _flag_style_issues(text: str) -> list[str]:
    """Judgment-required issues found by exact-phrase/pattern match - just
    surfaced for the style self-check pass to fix in context. Covers four
    distinct failure modes: literary/formal register, AI-cliché vocabulary,
    leftover English-style dashes, and RTL-unreadable English-term density."""
    flags = [m for m in _FORMAL_MARKERS if m in text]
    flags += [p for p in _AI_CLICHE_PHRASES if p in text]
    if _DASH_PATTERN.search(text):
        flags.append("em/en dash (—/–) - restructure the sentence around it")
    flags += _flag_dense_latin_runs(text)
    return flags


def _draft(item: dict[str, Any], article_text: str, is_full_article: bool,
           register_guide: str, anti_ai_guide: str,
           taxonomy: list[str]) -> dict[str, str]:
    system = (
        "You write for a personal Telegram channel about programming, dev "
        "tooling, and AI coding tools. Follow the register guide exactly, "
        "and avoid every pattern in the anti-AI-writing guide - write the "
        "way a Persian-speaking developer would explain the news to a "
        "colleague, not like a translated AI summary.\n\n"
        f"--- REGISTER GUIDE ---\n{register_guide}\n--- END REGISTER GUIDE ---\n\n"
        f"--- ANTI-AI-WRITING GUIDE ---\n{anti_ai_guide}\n"
        "--- END ANTI-AI-WRITING GUIDE ---\n\n"
        f"Relevant taxonomy tags available: {', '.join(taxonomy)}.\n\n"
        "Return ONLY valid JSON (no markdown fences): "
        '{"title_fa": "...", "body_fa": "...", "tags": ["..."]}. '
        "body_fa should be 3-5 sentences: what happened, why it matters to a "
        "developer, and what changed vs before, if relevant. "
        f"tags: at most {_MAX_TAGS} - the single most relevant categor"
        f"{'y' if _MAX_TAGS == 1 else 'ies'}, not every tag that could "
        "technically apply; these become hashtags on the channel, so more "
        "isn't better."
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


def _style_self_check(draft: dict[str, str], register_guide: str,
                       anti_ai_guide: str, style_flags: list[str]) -> dict[str, str]:
    if not style_flags:
        return draft  # nothing flagged, skip the call entirely

    system = (
        "You are reviewing a Persian draft against a register checklist AND "
        "an anti-AI-writing pattern guide, for a developer-focused Telegram "
        "channel. Revise ONLY where needed - don't rewrite lines that "
        "already fit.\n\n"
        f"--- REGISTER GUIDE ---\n{register_guide}\n--- END REGISTER GUIDE ---\n\n"
        f"--- ANTI-AI-WRITING GUIDE ---\n{anti_ai_guide}\n"
        "--- END ANTI-AI-WRITING GUIDE ---\n\n"
        "Also ask the self-check question from the anti-AI-writing guide: "
        "would a Persian-speaking developer who reads this channel daily "
        "sense anything translated, clichéd, or promotional in this text? "
        "If so, rewrite that specific part the way that developer would "
        "actually say it - without adding or removing any fact.\n\n"
        "Return ONLY valid JSON: {\"title_fa\": \"...\", \"body_fa\": \"...\", \"tags\": [...]}"
    )
    user = (
        f"Draft title: {draft['title_fa']}\nDraft body: {draft['body_fa']}\n"
        f"Tags: {draft.get('tags', [])}\n\n"
        f"The automated check flagged these phrases/patterns as present: "
        f"{', '.join(style_flags)}. Fix each one in context per the guides "
        f"above. Keep everything else unless it needs to change to keep the "
        f"passage coherent."
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
               register_guide: str, anti_ai_guide: str,
               taxonomy: list[str]) -> dict[str, Any]:
    """Runs the full draft -> mechanical fixes -> style self-check -> fact self-check pipeline."""
    draft = _draft(item, article_text, is_full_article, register_guide, anti_ai_guide, taxonomy)

    draft["title_fa"] = _mechanical_fixes(draft["title_fa"])
    draft["body_fa"] = _mechanical_fixes(draft["body_fa"])
    style_flags = _flag_style_issues(draft["title_fa"] + " " + draft["body_fa"])

    revised = _style_self_check(draft, register_guide, anti_ai_guide, style_flags)
    revised["title_fa"] = _mechanical_fixes(revised["title_fa"])
    revised["body_fa"] = _mechanical_fixes(revised["body_fa"])

    fact_check = _fact_grounding_self_check(revised, article_text, is_full_article)
    if not fact_check.get("ok", True):
        final_title = fact_check.get("corrected_title_fa") or revised["title_fa"]
        final_body = fact_check.get("corrected_body_fa") or revised["body_fa"]
        fact_issues = fact_check.get("issues", [])
    else:
        final_title, final_body = revised["title_fa"], revised["body_fa"]
        fact_issues = []

    # Final safety net: mechanical fixes are idempotent so re-running them
    # here is harmless even though most text already passed through them,
    # and the dash fallback belongs only here, once, as pure insurance after
    # every LLM pass (including the fact-check, which could in principle
    # reintroduce one by echoing source text) has already had its shot at
    # restructuring the sentence properly.
    final_title = _mechanical_fixes(final_title)
    final_body = _mechanical_fixes(final_body)
    if _DASH_PATTERN.search(final_title + final_body):
        final_title = _dash_fallback(final_title)
        final_body = _dash_fallback(final_body)

    return {
        **item,
        "title_fa": final_title,
        "body_fa": final_body,
        # Capped here as a backstop on top of the prompt instruction above -
        # deliver.py caps again independently when it also translates these
        # to Persian, so the limit holds even if one layer is skipped.
        "tags": (revised.get("tags") or [])[:_MAX_TAGS],
        "style_flags_found": style_flags,
        "fact_check_issues": fact_issues,
        "used_full_article": is_full_article,
    }
