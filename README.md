# programming-digest-bot

A daily pipeline that sources programming/dev-tooling news, scores and filters
it, has an LLM select and write it up in Persian, and DMs you the options on
Telegram with a pick / reject button. Posting to the channel itself stays
**entirely manual and outside this pipeline** — nothing here auto-posts
anything.

Built from `programming-channel-pipeline-plan.md` (a review of an earlier
plan) — see **"What this is based on"** below for the one important gap in
that source document.

## Architecture

```
sourcing.py       Stage 1: pull candidates from release feeds, vendor blogs,
                   HN, Lobsters, dev.to, Reddit
score.py          Stage 2: mechanical score + seen-link filter + threshold
                   with floor/ceiling
select_llm.py      Stage 3a: ONE LLM call — cluster same-story duplicates
                   across sources, judge which clusters are worthy
article_fetch.py  fetches full article text for the write stage (teaser
                   fallback on paywalls / JS-heavy pages)
write_llm.py       Stage 3b: draft -> regex pre-check (Arabic chars, formal
                   markers) -> LLM register self-check -> LLM fact-grounding
                   self-check
deliver.py        Stage 4: Telegram DMs — first message notifies, rest
                   silent; source link on every option; zero-day ping
pick_logger.py     Stage 5: polls Telegram for pick/reject button taps,
                   logs to data/picks.jsonl
propose.py         ties stages 1-4 together; run daily by
                   .github/workflows/propose.yml
collect_picks.py   runs pick_logger.py; run every ~15 min by
                   .github/workflows/collect_picks.yml
```

Flat-file state (`data/`), no database:
- `seen_links.json` — every URL ever sent, so it never resurfaces
- `pending_items.json` — today's shortlist, so a button tap later can be
  matched back to its title/url/tags
- `picks.jsonl` — the pick/reject log (append-only)
- `telegram_update_offset.txt` — Telegram `getUpdates` polling offset
- `last_run.txt` — a heartbeat, see the note on GitHub's 60-day rule below

All of it round-trips through git: each workflow run commits its own state
changes back to the repo.

## Setup

1. **Create a Telegram bot** via [@BotFather](https://t.me/BotFather), get
   its token. DM the bot once so it can message you, then get your numeric
   chat id from [@userinfobot](https://t.me/userinfobot).
2. **Get two free LLM API keys** - no card needed for either:
   - Gemini (primary; better Persian output, used for both selection and
     writing): [Google AI Studio](https://aistudio.google.com/apikey)
   - Groq (fallback only - kicks in if a Gemini call errors or gets
     rate-limited during the unattended daily run):
     [Groq Console](https://console.groq.com/keys)
3. **Fork/push this repo to GitHub**, then add repo secrets (Settings →
   Secrets and variables → Actions):
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `GEMINI_API_KEY`
   - `GROQ_API_KEY`
   - optionally repo **variables** `GEMINI_MODEL` / `GROQ_MODEL` to override
     the defaults (`gemini-flash-latest` / `llama-3.3-70b-versatile`)
4. Enable Actions on the repo if it's a fork. The two workflows
   (`propose.yml`, `collect_picks.yml`) are already scheduled — no further
   action needed.
5. **Local testing** (optional, before pushing): copy `.env.example` to
   `.env`, fill it in, `pip install -r requirements.txt`, then:
   ```
   python scripts/run_local.py sourcing   # just fetch, no LLM calls
   python scripts/run_local.py score      # + mechanical scoring
   python scripts/run_local.py select     # + LLM select/cluster (costs tokens)
   python scripts/run_local.py full       # entire pipeline, sends to Telegram for real
   python scripts/run_local.py picks      # poll for button taps once
   ```
   Local runs never commit to git — only the GitHub Actions workflows do.

## What's a placeholder vs. what's real

The document this was built from is a *review* of an earlier plan, not the
plan itself — it references a couple of things by name without including
their actual content:

- **`config/register.md`** — the review calls for reusing a `PERSIAN_REGISTER`
  string "verbatim" from an earlier project. I don't have that text, so
  `register.md` is a reasonable draft standing in for it. **If you have the
  real one, replace this file's contents** — nothing else needs to change,
  `write_llm.py` just loads it as a raw string.
- **`config/telegram_formatting.md`** — same situation for
  `TELEGRAM_FORMATTING`.

Everything else — sourcing tiers, scoring formula, the select/write split,
the two self-check passes, delivery behavior, pick logging, the GitHub
Actions architecture — is a direct, complete implementation of what the
review document specifies.

## Feeds and tuning

Edit `config/feeds.yaml` to add/remove:
- tracked repos for release feeds (the highest-precision tier — this was the
  review's main flagged gap in the original plan)
- vendor blogs, subreddits, dev.to tag filters
- scoring knobs: `score_threshold`, `min_candidates`/`max_candidates` (the
  floor/ceiling around the threshold cut), recency half-life, tier weights

## Note on GitHub's 60-day scheduled-workflow rule

GitHub auto-disables scheduled workflows on a repo with 60 days of no
activity, and per GitHub's own docs, only **new commits** reset that clock —
not workflow runs by themselves. `propose.py` writes `data/last_run.txt` on
every run specifically so there's always a real file change to commit, even
on a day when nothing clears the editorial bar. As long as
`.github/workflows/propose.yml`'s commit step keeps succeeding, this repo
never goes quiet enough to trip that rule — worth glancing at the Actions
tab occasionally to confirm the commit step is actually landing, since a
silently-failing push would reintroduce the risk.

## Extending later (not built)

- **Breaking-news fast path**: Stage 2's mechanical score already produces a
  number; one item wildly outscoring the last N days is a free trigger for
  an off-schedule run. Not built — the review flagged this as real added
  complexity for a handful of days a year, worth adding only if it actually
  comes up.
- **Phase 3 personalization**: `picks.jsonl` already distinguishes pick vs.
  reject vs. untouched, which is the data a future ranking pass would need.
  No ranking model here yet.
# programming-digest
