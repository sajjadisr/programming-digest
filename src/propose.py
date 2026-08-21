"""Entry point for the daily proposal run (.github/workflows/propose.yml).

Pipeline: sourcing -> mechanical score/filter -> LLM select+cluster ->
article fetch -> LLM write (draft + two self-checks) -> deliver -> persist state.

State persisted for the next run / for pick_logger.py:
  - data/seen_links.json     : every URL ever sent (any cluster member), so it
                                never resurfaces even under a different canonical pick
  - data/pending_items.json  : today's shortlist keyed by canonical_id, so
                                pick_logger.py can attach title/url/tags to a
                                pick/reject decision when the button is tapped
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from article_fetch import fetch_article_text
from deliver import send_daily_options
from feedback import build_feedback_block
from score import filter_seen, score_and_cut
from select_llm import select_and_cluster
from sourcing import collect_all
from utils import (
    LAST_RUN_PATH,
    PENDING_ITEMS_PATH,
    SEEN_LINKS_PATH,
    anti_ai_guide,
    env,
    load_feeds_config,
    load_json,
    register_guide,
    save_json,
)
from write_llm import write_item


def _cap_per_key(clusters: list[dict], key_fn, limit: int | None, label: str) -> list[dict]:
    """Caps every group (grouped by key_fn) to at most `limit` items, keeping
    the highest mech_score in each group. Used for the per-source diversity
    guardrail. Nothing is dropped for good - see max_write_per_run's comment
    in config/feeds.yaml for why capped-here-today just means candidate-again
    -tomorrow, not lost."""
    if not limit:
        return clusters
    buckets: dict[Any, list[dict]] = {}
    for c in clusters:
        buckets.setdefault(key_fn(c), []).append(c)
    kept: list[dict] = []
    deferred = 0
    for bucket in buckets.values():
        bucket.sort(key=lambda c: c.get("mech_score", 0), reverse=True)
        kept.extend(bucket[:limit])
        deferred += max(0, len(bucket) - limit)
    if deferred:
        print(f"[propose] capping to {limit} per {label} ({deferred} deferred to a future run)")
    return sorted(kept, key=lambda c: c.get("mech_score", 0), reverse=True)


def _cap_one_category(
    clusters: list[dict], guess_key: str, category_value: str, limit: int | None
) -> list[dict]:
    """Caps only ONE specific category's items to at most `limit`, leaving
    every other category's items untouched (unlike _cap_per_key, which caps
    every group). Used for the ai_coding_tools volume cap."""
    if not limit:
        return clusters
    matching = [c for c in clusters if c.get(guess_key) == category_value]
    if len(matching) <= limit:
        return clusters
    matching.sort(key=lambda c: c.get("mech_score", 0), reverse=True)
    keep_ids = {id(c) for c in matching[:limit]}
    deferred = len(matching) - limit
    print(
        f"[propose] capping {category_value!r} to top {limit} by mech_score "
        f"({deferred} deferred to a future run)"
    )
    return [c for c in clusters if c.get(guess_key) != category_value or id(c) in keep_ids]


def main() -> None:
    token = env("TELEGRAM_BOT_TOKEN", required=True)
    chat_id = env("TELEGRAM_CHAT_ID", required=True)
    # GEMINI_API_KEY / GROQ_API_KEY are read directly by llm_client.py from the environment

    config = load_feeds_config()
    seen_links = set(load_json(SEEN_LINKS_PATH, []))

    print("[propose] sourcing...")
    raw_candidates = collect_all(config)
    print(f"[propose] {len(raw_candidates)} raw candidates fetched")

    fresh = filter_seen(raw_candidates, seen_links)
    print(f"[propose] {len(fresh)} candidates after removing already-seen URLs")

    scored = score_and_cut(fresh, config["scoring"])
    print(f"[propose] {len(scored)} candidates pass the mechanical score/filter -> LLM select")

    feedback_block = build_feedback_block()
    if feedback_block:
        n_lines = feedback_block.count("\n- ")
        print(f"[propose] including {n_lines} past pick/reject decision(s) as select-stage feedback")

    worthy_clusters = select_and_cluster(scored, feedback_block=feedback_block)
    print(f"[propose] {len(worthy_clusters)} clusters judged worthy by the LLM select stage")

    # Diversity guardrails, applied AFTER the LLM's own judgment (select_llm.py
    # is also told to weigh both of these) but BEFORE the write stage, so a
    # capped-out item never costs a write-stage LLM call in the first place.
    # See config/feeds.yaml's max_per_source_per_run / max_ai_coding_tools_per_run
    # comments for why these exist as a mechanical backstop rather than trusting
    # the LLM's judgment alone.
    worthy_clusters = _cap_per_key(
        worthy_clusters,
        key_fn=lambda c: c.get("source", "?"),
        limit=config["scoring"].get("max_per_source_per_run"),
        label="source",
    )
    worthy_clusters = _cap_one_category(
        worthy_clusters,
        guess_key="taxonomy_guess",
        category_value="ai_coding_tools",
        limit=config["scoring"].get("max_ai_coding_tools_per_run"),
    )

    # Cap + prioritize before spending any LLM calls on the write stage - see
    # config/feeds.yaml's max_write_per_run comment for why. Clusters left
    # over aren't lost or marked seen, so they're just candidates again next
    # run (module-fresh Gemini daily quota and all).
    max_write = config["scoring"].get("max_write_per_run")
    if max_write and len(worthy_clusters) > max_write:
        worthy_clusters = sorted(worthy_clusters, key=lambda c: c.get("mech_score", 0), reverse=True)
        deferred = len(worthy_clusters) - max_write
        worthy_clusters = worthy_clusters[:max_write]
        print(f"[propose] capping write stage to top {max_write} by mech_score "
              f"({deferred} deferred to a future run)")

    guide = register_guide()
    anti_ai = anti_ai_guide()
    # config/feeds.yaml's taxonomy is [{key, label_fa}, ...]: `key` is what
    # write_llm.py's draft prompt matches "tags" against (stable English
    # slugs, shared with score.py's TAXONOMY_KEYWORDS), `label_fa` is the
    # single source of truth deliver.py uses to render hashtags in Persian -
    # see feeds.yaml's comment on why that translation is code-enforced
    # rather than left to the writing LLM.
    taxonomy_cfg = config.get("taxonomy", [])
    taxonomy_keys = [t["key"] for t in taxonomy_cfg]
    taxonomy_labels_fa = {t["key"]: t["label_fa"] for t in taxonomy_cfg}

    final_items = []
    for i, cluster in enumerate(worthy_clusters):
        # One item hitting a rate limit or an unparseable LLM response
        # shouldn't cost the whole run - previously an exception here
        # propagated out of main(), so send_daily_options() never ran and
        # every item already written that run (plus all of today's mechanical
        # scoring/select-stage LLM spend) was thrown away, and next run would
        # just redo the same work. Log and skip instead; a skipped item isn't
        # marked seen, so it's picked up again next run.
        try:
            article_text, is_full = fetch_article_text(cluster["url"], cluster.get("summary", ""))
            written = write_item(cluster, article_text, is_full, guide, anti_ai, taxonomy_keys)
        except Exception as e:
            print(f"[propose]   SKIPPED {cluster.get('title', '?')[:60]!r}: {e!r}")
            continue
        final_items.append(written)
        print(
            f"[propose]   wrote: {written['title_fa'][:60]!r} "
            f"(full_article={is_full}, style_flags={len(written['style_flags_found'])}, "
            f"fact_issues={len(written['fact_check_issues'])})"
        )
        # Cheap pacing: write_item() is 2-3 LLM calls, and Groq's free-tier
        # limit is per-minute (TPM). Spacing items out a couple seconds keeps
        # a full batch from landing in the same rate-limit window instead of
        # spread across it - costs at most ~max_write_per_run * 2 seconds.
        if i < len(worthy_clusters) - 1:
            time.sleep(2)

    send_daily_options(token, chat_id, final_items, taxonomy_labels_fa)
    print(f"[propose] sent {len(final_items)} option(s) to Telegram (or a zero-day ping)")

    # Persist state for tomorrow's run and for pick_logger.py.
    all_sent_urls = seen_links | {u for it in final_items for u in it["member_urls"]}
    save_json(SEEN_LINKS_PATH, sorted(all_sent_urls))

    pending = {
        it["canonical_id"]: {
            "title": it["title"],
            "title_fa": it["title_fa"],
            "url": it["url"],
            "tags": it.get("tags", []),
            # Carried through so a later pick/reject tap (pick_logger.py) can
            # log rich-enough context for feedback.py's calibration block -
            # see feedback.py for how these get used.
            "source": it.get("source"),
            "taxonomy_guess": it.get("taxonomy_guess"),
            "select_reason": it.get("select_reason", ""),
        }
        for it in final_items
    }
    # Merge rather than overwrite: items from prior days may still be un-tapped.
    existing_pending = load_json(PENDING_ITEMS_PATH, {})
    existing_pending.update(pending)
    save_json(PENDING_ITEMS_PATH, existing_pending)

    # Guarantees a real file change (and therefore a real commit) every run,
    # even on a zero-news day - see README's note on GitHub's 60-day
    # scheduled-workflow auto-disable, which only new commits reset.
    LAST_RUN_PATH.write_text(datetime.now(tz=timezone.utc).isoformat() + "\n")


if __name__ == "__main__":
    main()
