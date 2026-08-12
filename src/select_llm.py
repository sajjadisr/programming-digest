"""Stage 3a: selection.

This is the LLM call the review pulls out into its own step: decide which
candidates are worthy of the channel, and cluster same-story-different-URL
duplicates (an HN thread, a vendor post, and an aggregator writeup about the
same release, say) into one item. The writing stage (write_llm.py) then works
from this locked list and spends its whole budget on writing, not also on
judgment calls about inclusion.
"""
from __future__ import annotations

from typing import Any

from llm_client import complete_json

SYSTEM_PROMPT = """You are the editorial gate for a personal Telegram channel about \
programming, dev tooling, and AI coding tools, written for working developers \
who want signal, not hype.

You will be given a list of candidate items (id, title, url, source, mechanical \
score, short teaser). Your job has two parts:

1. CLUSTER: group items that cover the same underlying story (e.g. an HN \
   thread, a vendor blog post, and an aggregator writeup about the same \
   release) into a single cluster. Pick the single best canonical item per \
   cluster - prefer the primary source (vendor blog, official release notes) \
   over commentary/aggregation when one is present. Items with nothing else \
   covering the same story are their own single-item cluster.

2. JUDGE: for each cluster, decide if it clears the bar for this channel: \
   genuinely useful/interesting to a developer audience, not filler, not \
   low-effort reposts, not marketing fluff with no substance. A high \
   mechanical score is a signal, not a verdict - use your judgment.

Return ONLY valid JSON (no markdown fences, no commentary) matching this shape:
{
  "clusters": [
    {
      "canonical_id": "<id of the best item in this cluster>",
      "member_ids": ["<id1>", "<id2>", ...],
      "worthy": true or false,
      "reason": "<one short sentence, for your own future reference>"
    },
    ...
  ]
}

Include every input id exactly once across all clusters, worthy or not."""


def _format_candidates(items: list[dict[str, Any]]) -> str:
    lines = []
    for it in items:
        teaser = (it.get("summary") or "").replace("\n", " ").strip()[:280]
        lines.append(
            f"- id: {it['id']}\n"
            f"  title: {it['title']}\n"
            f"  url: {it['url']}\n"
            f"  source: {it['source']} (tier {it['tier']}, mech_score {it['mech_score']})\n"
            f"  teaser: {teaser}"
        )
    return "\n".join(lines)


def select_and_cluster(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Returns the list of worthy clusters, each carrying its canonical item's data.

    Output shape per cluster:
      {canonical_id, member_ids, member_urls, reason, <...canonical item fields>}
    """
    if not items:
        return []

    by_id = {it["id"]: it for it in items}
    user_prompt = (
        f"{len(items)} candidate items follow. Cluster and judge them per your instructions.\n\n"
        + _format_candidates(items)
    )

    result = complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=8192)
    clusters = result.get("clusters", [])

    worthy_clusters = []
    for cluster in clusters:
        if not cluster.get("worthy"):
            continue
        canonical_id = cluster.get("canonical_id")
        canonical_item = by_id.get(canonical_id)
        if canonical_item is None:
            # LLM hallucinated an id; skip defensively rather than crash the run
            print(f"[select_llm] WARN: unknown canonical_id {canonical_id!r}, skipping cluster")
            continue
        member_ids = [m for m in cluster.get("member_ids", []) if m in by_id]
        worthy_clusters.append(
            {
                **canonical_item,
                "canonical_id": canonical_id,
                "member_ids": member_ids or [canonical_id],
                "member_urls": [by_id[m]["url"] for m in (member_ids or [canonical_id])],
                "select_reason": cluster.get("reason", ""),
            }
        )

    return worthy_clusters
