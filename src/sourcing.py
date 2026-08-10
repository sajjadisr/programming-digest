"""Stage 1: sourcing.

Pulls raw candidates from every configured feed tier:
  tier 1 — release/changelog Atom feeds (github.com/{org}/{repo}/releases.atom) and vendor blogs
  tier 2 — HN, Lobsters
  tier 3 — dev.to, Reddit (filtered hard, same as dev.to)

Each candidate is normalized to a plain dict so score.py doesn't need to know
where anything came from:
  {id, title, url, source, tier, published_iso, summary, engagement}
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any

import feedparser
import requests

USER_AGENT = "programming-digest-bot/1.0 (+personal Telegram digest; low volume)"


def _item_id(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _parse_published(entry) -> str:
    for key in ("published_parsed", "updated_parsed"):
        val = getattr(entry, key, None)
        if val:
            return datetime.fromtimestamp(time.mktime(val), tz=timezone.utc).isoformat()
    return datetime.now(tz=timezone.utc).isoformat()


def _fetch_rss(url: str, source: str, tier: int, timeout: int = 15) -> list[dict[str, Any]]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as e:  # network hiccups shouldn't kill the whole run
        print(f"[sourcing] WARN: failed to fetch {source} ({url}): {e}")
        return []

    items = []
    for entry in parsed.entries:
        link = getattr(entry, "link", None)
        title = getattr(entry, "title", None)
        if not link or not title:
            continue
        items.append(
            {
                "id": _item_id(link),
                "title": title.strip(),
                "url": link.strip(),
                "source": source,
                "tier": tier,
                "published_iso": _parse_published(entry),
                "summary": (getattr(entry, "summary", "") or "").strip(),
                "engagement": None,  # filled in below for sources that expose it (HN)
            }
        )
    return items


def _fetch_hn(url: str, tier: int) -> list[dict[str, Any]]:
    # hnrss.org includes point count in the title-adjacent description; keep it simple
    # and just treat HN's own curation (the "best" feed) as the engagement signal.
    items = _fetch_rss(url, "hacker_news", tier)
    for it in items:
        it["engagement"] = 1.0  # baseline; HN's "best" feed is already pre-filtered by votes
    return items


def _fetch_reddit(subreddit: str, tier: int, timeout: int = 15) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=day&limit=25"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[sourcing] WARN: failed to fetch reddit r/{subreddit}: {e}")
        return []

    items = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        link = post.get("url_overridden_by_dest") or (
            f"https://reddit.com{post.get('permalink', '')}"
        )
        title = post.get("title")
        if not link or not title:
            continue
        created = post.get("created_utc")
        published_iso = (
            datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
            if created
            else datetime.now(tz=timezone.utc).isoformat()
        )
        items.append(
            {
                "id": _item_id(link),
                "title": title.strip(),
                "url": link.strip(),
                "source": f"reddit:r/{subreddit}",
                "tier": tier,
                "published_iso": published_iso,
                "summary": (post.get("selftext") or "")[:500],
                "engagement": float(post.get("score", 0)),
            }
        )
    return items


def collect_all(feeds_config: dict) -> list[dict[str, Any]]:
    """Fetch every configured source and return a flat, deduped-by-URL list."""
    candidates: dict[str, dict[str, Any]] = {}

    def _add_many(items: list[dict[str, Any]]) -> None:
        for it in items:
            candidates.setdefault(it["url"], it)

    agg = feeds_config.get("aggregators", [])
    for feed in agg:
        if feed["name"] == "hacker_news":
            _add_many(_fetch_hn(feed["url"], feed["tier"]))
        elif feed["name"] == "devto":
            items = _fetch_rss(feed["url"], "dev.to", feed["tier"])
            _add_many(items)
        else:
            _add_many(_fetch_rss(feed["url"], feed["name"], feed["tier"]))

    reddit_cfg = feeds_config.get("reddit", {})
    for sub in reddit_cfg.get("subreddits", []):
        _add_many(_fetch_reddit(sub, reddit_cfg.get("tier", 3)))

    vendor_cfg = feeds_config.get("vendor_blogs", {})
    for feed in vendor_cfg.get("feeds", []):
        _add_many(_fetch_rss(feed["url"], feed["name"], vendor_cfg.get("tier", 1)))

    release_cfg = feeds_config.get("release_feeds", {})
    for repo in release_cfg.get("repos", []):
        url = f"https://github.com/{repo}/releases.atom"
        _add_many(_fetch_rss(url, f"releases:{repo}", release_cfg.get("tier", 1)))

    return list(candidates.values())
