"""Stage 2a: mechanical scoring and filtering.

This is deliberately the "cheap deterministic facts get a formula" half of the
score & filter stage. Judgment calls (is this actually good, is this a dup of
that) belong to the LLM select stage in select_llm.py, not here.

score = tier_weight + engagement_component + recency_decay + keyword_match_bonus

Then: keep everything >= score_threshold, but bound the count between
min_candidates and max_candidates so a slow news day doesn't send 0 candidates
to the LLM and a huge news day doesn't send 300.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

KEYWORD_BONUS = 1.5
TAXONOMY_KEYWORDS = {
    "languages_runtimes": ["python", "rust", "typescript", "javascript", "go ", "golang", "node"],
    "frontend_frameworks": ["react", "vue", "svelte", "next.js", "angular"],
    "ai_coding_tools": ["copilot", "claude code", "cursor", "windsurf", "codex", "ai agent", "llm"],
    "dev_tooling_build_systems": ["vite", "webpack", "esbuild", "turborepo", "bun", "deno"],
    "infra_cloud": ["kubernetes", "docker", "aws", "vercel", "cloudflare"],
    "databases": ["postgres", "sqlite", "redis", "mysql"],
    "security": ["cve", "vulnerability", "security advisory", "exploit"],
    "open_source_releases": ["release", "changelog", "v1.", "v2.", "v3.", "ga release"],
}


def _recency_decay(published_iso: str, half_life_hours: float) -> float:
    try:
        published = datetime.fromisoformat(published_iso)
    except ValueError:
        return 0.5
    age_hours = (datetime.now(tz=timezone.utc) - published).total_seconds() / 3600
    age_hours = max(age_hours, 0)
    return 0.5 ** (age_hours / half_life_hours)


def _keyword_bonus(title: str, summary: str) -> float:
    text = f"{title} {summary}".lower()
    hits = 0
    for keywords in TAXONOMY_KEYWORDS.values():
        if any(kw in text for kw in keywords):
            hits += 1
    return min(hits, 3) * KEYWORD_BONUS  # cap so one item can't dominate purely on keyword spam


def _guess_primary_taxonomy(title: str, summary: str) -> str | None:
    """Cheap keyword-count guess at the single best-fit taxonomy category.

    Zero extra LLM calls/tokens - reuses the same TAXONOMY_KEYWORDS table as
    _keyword_bonus above, just keeps *which* category won instead of only a
    count. This is deliberately NOT sent to the LLM select/write stages and
    is NOT what ends up in the delivered hashtags (select_llm.py's judgment
    and write_llm.py's own "tags" output are the real, higher-quality signal
    for those). It exists purely so propose.py can apply a cheap mechanical
    cap - e.g. "no more than N ai_coding_tools items per run" - before
    spending any LLM calls on the write stage. Ties keep the first category
    in TAXONOMY_KEYWORDS' (insertion) order, which is an acceptable amount of
    arbitrariness for a rough guess used only as a volume cap, not a verdict.
    """
    text = f"{title} {summary}".lower()
    best_key, best_hits = None, 0
    for key, keywords in TAXONOMY_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > best_hits:
            best_key, best_hits = key, hits
    return best_key


def score_item(item: dict[str, Any], scoring_cfg: dict) -> float:
    tier_weight = scoring_cfg["tier_weight"].get(item["tier"], 1.0)
    engagement = item.get("engagement")
    engagement_component = math.log1p(engagement) if engagement else 0.0
    recency = _recency_decay(item["published_iso"], scoring_cfg["recency_half_life_hours"])
    keyword = _keyword_bonus(item["title"], item.get("summary", ""))
    return round(tier_weight + engagement_component + 2 * recency + keyword, 3)


def filter_seen(items: list[dict], seen_links: set[str]) -> list[dict]:
    """Drop items whose exact URL we've already sent before (Stage 2's cheap dedup)."""
    return [it for it in items if it["url"] not in seen_links]


def score_and_cut(items: list[dict], scoring_cfg: dict) -> list[dict]:
    for it in items:
        it["mech_score"] = score_item(it, scoring_cfg)
        it["taxonomy_guess"] = _guess_primary_taxonomy(it["title"], it.get("summary", ""))

    ranked = sorted(items, key=lambda x: x["mech_score"], reverse=True)
    threshold = scoring_cfg["score_threshold"]
    above = [it for it in ranked if it["mech_score"] >= threshold]

    min_c = scoring_cfg["min_candidates"]
    max_c = scoring_cfg["max_candidates"]

    if len(above) < min_c:
        # floor: backfill by rank even if below threshold, so a quiet day still
        # gets a shortlist for the LLM to judge (it may still reject all of them).
        result = ranked[:min_c]
    else:
        result = above[:max_c]

    return result
