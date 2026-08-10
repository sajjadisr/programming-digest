"""Fetches full article text for the write stage.

The plan originally fed the LLM the RSS title + summary. The review's
strongest change to the write stage is to feed it the real article body
instead, falling back to the RSS teaser when extraction fails (paywalls,
JS-heavy pages) — thin source material is the most common reason AI writing
drifts into generic padding.
"""
from __future__ import annotations

import requests
import trafilatura

USER_AGENT = "programming-digest-bot/1.0 (+personal Telegram digest; low volume)"
MAX_CHARS = 12000  # keep prompts bounded; full changelog/blog posts rarely exceed this


def fetch_article_text(url: str, teaser: str, timeout: int = 15) -> tuple[str, bool]:
    """Returns (text, is_full_article). Falls back to the teaser on any failure."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        extracted = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
        if extracted and len(extracted.strip()) > 200:  # guard against near-empty extractions
            return extracted.strip()[:MAX_CHARS], True
    except Exception as e:
        print(f"[article_fetch] WARN: extraction failed for {url}: {e}")

    return (teaser or "").strip(), False
