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
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from article_fetch import fetch_article_text
from deliver import send_daily_options
from score import filter_seen, score_and_cut
from select_llm import select_and_cluster
from sourcing import collect_all
from utils import (
    LAST_RUN_PATH,
    PENDING_ITEMS_PATH,
    SEEN_LINKS_PATH,
    env,
    load_feeds_config,
    load_json,
    register_guide,
    save_json,
)
from write_llm import write_item


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

    worthy_clusters = select_and_cluster(scored)
    print(f"[propose] {len(worthy_clusters)} clusters judged worthy by the LLM select stage")

    guide = register_guide()
    taxonomy = config.get("taxonomy", [])

    final_items = []
    for cluster in worthy_clusters:
        article_text, is_full = fetch_article_text(cluster["url"], cluster.get("summary", ""))
        written = write_item(cluster, article_text, is_full, guide, taxonomy)
        final_items.append(written)
        print(
            f"[propose]   wrote: {written['title_fa'][:60]!r} "
            f"(full_article={is_full}, fact_issues={len(written['fact_check_issues'])})"
        )

    send_daily_options(token, chat_id, final_items)
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
