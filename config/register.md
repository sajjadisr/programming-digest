<!--
PLACEHOLDER — the review this build is based on references a `PERSIAN_REGISTER`
string that's meant to be "reused verbatim" from an earlier project. I don't have
that actual text, so this is a reasonable draft standing in for it.
If you have the real one, replace this whole file with it — src/write.py loads
it as a raw string and drops it into both the drafting prompt and the register
self-check prompt, so nothing else needs to change.
-->

# Persian register guide (draft — replace with your real one if you have it)

Write in everyday spoken-register Persian (فارسی محاوره‌ای), the way a developer
would explain something to a colleague in a Telegram channel — not the register
of a translated technical book.

Concretely:
- Use everyday verb forms and endings, not the stiff literary/written register
  (e.g. "می‌کنه" over "می‌کند" where the channel's existing voice already does this —
  match whatever register the channel has been using, don't invent a new one here).
- Use ی and ک (Persian yeh/kaf), never ي and ك (Arabic yeh/kaf). This is one of the
  mechanical, regex-catchable rules — see the character fixes in
  `src/write_llm.py`, which run before the LLM self-check pass even starts.
- Keep well-established English technical terms in Latin script rather than
  forcing an awkward Persian transliteration (e.g. "runtime", "API", "release" —
  see the glossary below). Don't force-translate proper nouns or product names.
- Avoid word-for-word sentence structures carried over from English source
  text. Concretely: read the source sentence for its meaning, forget it was in
  English, then rebuild it the way a Persian-speaking developer would say it
  from scratch — Persian clause and verb order, not English order with Persian
  words substituted in. After writing, read it back and ask whether a
  Persian-only speaker would understand it immediately or need to pause and
  re-parse it; if it needs a second pass, rewrite it. (Full before/after
  examples of this specific failure mode are in
  `persian_anti_ai_patterns.md` §1 — read that file too, not just this one;
  `write_llm.py` loads both into the same prompts.)
- 3–5 sentences per item: what happened, why it's worth 30 seconds of a
  developer's attention, and (if relevant) what changed vs. before.
- No filler throat-clearing ("در دنیای امروز فناوری...", "لازم به ذکر است که...").
  Start with the actual news. `persian_anti_ai_patterns.md` has a longer list
  of these stock phrases and other AI tells beyond just formality/register —
  this file is about *register* (colloquial vs. literary), that one is about
  *sounding AI-written* regardless of register.

## English-term glossary (extend as you go)
Keep as-is, don't transliterate: API, SDK, runtime, release, build, deploy,
repo, pull request, merge, backend, frontend, framework, compiler, benchmark,
open source, changelog.
