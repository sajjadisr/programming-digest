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
programming and dev tooling, written for working developers - beginners \
through senior engineers - who want signal, not hype.

You will be given a list of candidate items (id, title, url, source, mechanical \
score, short teaser). Your job has two parts:

1. CLUSTER: group items that cover the same underlying story (e.g. an HN \
   thread, a vendor blog post, and an aggregator writeup about the same \
   release) into a single cluster. Pick the single best canonical item per \
   cluster - prefer the primary source (vendor blog, official release notes) \
   over commentary/aggregation when one is present. Items with nothing else \
   covering the same story are their own single-item cluster.

2. JUDGE: for each cluster, decide if it clears the bar for this channel. Be \
   a genuinely selective editor, not a rubber stamp - a high mechanical score \
   only means a vendor posted it recently and it matched some keywords, not \
   that it's worth a subscriber's attention. Apply these tests:

   - BROAD RELEVANCE, not just "this vendor published something." A post \
     from one company's own engineering blog about its own internal \
     infrastructure (e.g. "we migrated our internal job queue from X to Y," \
     "how we run our own build fleet") is interesting mainly to that \
     vendor's own customers/users, not to developers broadly. Ask: would a \
     developer who doesn't use this specific vendor's platform still want to \
     know this? If the honest answer is no, it's probably not worthy even at \
     a high mechanical score - weigh this heavily, it's the single biggest \
     reason weak/uninteresting items have slipped through before.
   - SUBSTANCE over motion. Not filler, not a low-effort repost, not \
     marketing copy with no concrete detail, not a routine patch/point-release \
     with nothing notable in it.
   - AI CODING TOOLS get extra scrutiny, not a pass. This category (agent \
     features, IDE/CLI coding assistants, SDK/harness adapters, sandboxing, \
     "vibe coding" tooling) floods the candidate pool because vendors ship it \
     constantly - if you judge it by the same bar as everything else, it will \
     dominate every day's picks and crowd out general programming news, which \
     has happened before and is exactly what this channel doesn't want. Mark \
     an AI-coding-tools item worthy only if it's genuinely major: a real \
     capability landmark, a new de facto standard, a significant security/ \
     safety development - not a routine version bump, a minor adapter/ \
     integration between two tools, or an internal engineering write-up about \
     running such a tool. When in doubt on this category specifically, don't \
     mark it worthy; there will be more AI-coding-tools news tomorrow that \
     clears the bar more obviously, and every other category doesn't get \
     that same daily flood to draw from.
   - SOURCE VARIETY is worth factoring in when candidates are otherwise close. \
     If several borderline items are all from the same source and one clearly \
     weaker item is the only representative of a different source/ecosystem, \
     that's a legitimate reason to lean toward the latter - a channel that's \
     wall-to-wall one vendor is worse than one with real range, even before \
     any mechanical per-source cap kicks in downstream.

If earlier human pick/reject decisions are included below, they're real \
signal about this specific channel's taste - weight them accordingly, \
especially for calibrating borderline cases and the ai_coding_tools bar \
above.

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
        # Trimmed from 280 - at max_candidates=40 (config/feeds.yaml) the
        # full-length version pushed this prompt's input tokens high enough
        # that, combined with this call's 8192-token output budget, a Groq
        # fallback run (12000 TPM on the free tier) got rejected outright
        # with a 413 before it could even try. 140 chars is still enough for
        # the LLM to judge relevance; the canonical article text isn't sent
        # here at all, just enough to cluster and gate on.
        teaser = (it.get("summary") or "").replace("\n", " ").strip()[:140]
        lines.append(
            f"- id: {it['id']}\n"
            f"  title: {it['title']}\n"
            f"  url: {it['url']}\n"
            f"  source: {it['source']} (tier {it['tier']}, mech_score {it['mech_score']})\n"
            f"  teaser: {teaser}"
        )
    return "\n".join(lines)


def select_and_cluster(
    items: list[dict[str, Any]], feedback_block: str = ""
) -> list[dict[str, Any]]:
    """Returns the list of worthy clusters, each carrying its canonical item's data.

    Output shape per cluster:
      {canonical_id, member_ids, member_urls, reason, <...canonical item fields>}

    feedback_block: optional pre-formatted block of recent human pick/reject
    decisions from data/picks.jsonl (see feedback.py), prepended to the user
    prompt so operator button taps actually shape future runs instead of just
    sitting in a log file. Empty string (the default) if there's no history
    yet or the caller doesn't want to use it - the prompt reads fine either way.
    """
    if not items:
        return []

    by_id = {it["id"]: it for it in items}
    user_prompt = (
        (feedback_block + "\n\n" if feedback_block else "")
        + f"{len(items)} candidate items follow. Cluster and judge them per your instructions.\n\n"
        + _format_candidates(items)
    )

    # 6144 rather than the original 8192: with the teaser trim above and
    # config/feeds.yaml's max_candidates lowered to 30, the clustered output
    # for a full batch comes in well under this, but it's still enough
    # headroom to avoid the mid-object truncation that caused the very first
    # version of this bug (see llm_client.py's docstring). Kept here instead
    # of raised further because every token here also counts against Groq's
    # per-minute cap when Gemini isn't available.
    result = complete_json(SYSTEM_PROMPT, user_prompt, max_tokens=6144)
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
