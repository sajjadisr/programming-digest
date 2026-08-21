<!--
PLACEHOLDER — the review this build is based on references a `PERSIAN_REGISTER`
string that's meant to be "reused verbatim" from an earlier project. I don't have
that actual text, so this is a reasonable draft standing in for it.
If you have the real one, replace this whole file's content with it — src/write_llm.py loads
it as a raw string and drops it into both the drafting prompt and the register
self-check prompt, so nothing else needs to change. If you do replace it, keep
(or port over) the "English-term density," "Persian vs. Latin vs. finglish,"
and "explaining unfamiliar names" sections below — those were added after
real reader complaints about specific published items, not part of the
original placeholder.
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
- **Hashtags/"tags"**: at most 2, the single most relevant taxonomy
  categor(y/ies), never a running tally of every tag that could technically
  apply. `deliver.py` also caps and translates these to Persian
  mechanically — the field is still worth getting right at the source
  because it's what `deliver.py` translates *from*.

## Persian, Latin script, or finglish — pick one per term, deliberately

This channel's readers flagged real items where English words were used
where they didn't need to be, AND items where the *specific* problem was too
many separate English chunks packed into one sentence (see the next section).
Both come from the same root cause: treating "keep English jargon in Latin
script" as a blanket license instead of a per-word decision. Use this order
of preference instead, for every technical term:

1. **A native Persian word, if Persian-speaking developers actually say it
   that way out loud.** سرور، کاربر، نسخه، مرورگر، حافظه، پایگاه‌داده، فایل،
   خط‌فرمان. Don't reach for English or finglish just because the source
   article used the English word — check what a developer would actually
   *say*, not what the article wrote.
2. **Unmodified Latin script, for things that are names, not words**:
   product/company/library names (Vercel, Bun, DynamoDB, GitHub), code
   identifiers and function calls (`Bun.serve()`, `useState()`), file paths,
   version numbers, and acronyms so standardized that spelling them out in
   Persian letters would look wrong even to the engineers who use them daily
   (API, SDK, CLI, npm, git). **Never finglish these** — writing a product's
   own name in Persian letters doesn't make it more readable, it makes it
   harder to recognize and impossible to search for later.
3. **Finglish (Persian-letter spelling), only for loanwords that satisfy
   ALL of**: (a) no natural Persian word for it is in real use, (b) it's
   already completely normal in spoken developer Persian — کانتینر، دیپلوی،
   ریپو، مرج، بیلد، پروداکشن, and (c) writing it in Latin script would hurt
   the sentence's flow more than the finglish spelling would. If you're not
   sure a word clears all three, it doesn't belong here — it's probably tier
   1 or tier 2 instead.

**Concrete mistake to avoid** (this actually happened): a source article
about "Vercel Managed Images" got summarized with the generic noun "image"
finglished as `ایمیج`. That's wrong on two counts at once — the *product
name* ("Vercel Managed Images") is tier 2 (keep it in Latin, it's a name),
and the *generic word* "image" is tier 1 (`تصویر` is the normal Persian word
developers use; there was no reason to finglish it).

### English-term glossary (tier 2 — extend as you go)
Keep as-is, don't transliterate: API, SDK, runtime, release, build, deploy,
repo, pull request, merge, backend, frontend, framework, compiler, benchmark,
open source, changelog.

## English-term density and placement (RTL readability)

Even words that correctly belong in Latin script per the rule above can make
a sentence unreadable if there are too many of them close together — Persian
is RTL and English is LTR, so every switch between them is a direction
reversal for the reader's eye. A sentence with several separate English
chunks scattered through it, each surrounded by only a word or two of
Persian, reads as visually choppy even when every individual word choice was
"correct." This is a genuinely different failure mode from picking the wrong
script for a word (the section above) — it's about *how many* switches one
sentence asks the reader to make, regardless of which words are involved.

**Rule: at most 2 separate Latin-script terms per sentence.** If the
underlying fact needs more than that, do one of:
- Pick the 1–2 terms that actually matter and describe the rest in plain
  Persian instead of naming every identifier.
- Split into two sentences, each with its own budget of ≤2 terms.
- Move a cluster of related names into a short aside instead of weaving
  them mid-clause.

**Before** (4 separate English chunks in one sentence — this is a real
example a reader flagged as unreadable):
> Bun runtime تو Vercel Functions حالا می‌تونه Bun.serve() رو به‌عنوان ورودی‌کد بپذیره

**After** (down to 2, and the two that remain are placed together instead of
alternating with Persian mid-clause):
> حالا تو Vercel Functions می‌شه از Bun.serve() به‌عنوان نقطه‌ی شروع کد استفاده کرد

`src/write_llm.py` mechanically counts Latin-script chunks per sentence and
flags any sentence over the limit for the style self-check pass to fix — but
the fix itself (which 1–2 terms to keep, how to restructure) is a judgment
call the mechanical pass can't make, which is why it's documented here.

## Audience: explain unfamiliar names, don't assume

This channel's readers span complete beginners to senior engineers. Don't
assume a tool, library, or technique name is something every reader already
knows just because it's common in your own training data or because the
source article didn't bother explaining it (the source's audience is that
vendor's existing users — this channel's audience is broader).

**Test**: would a second-year CS student or a self-taught junior developer
recognize this name on sight? If not — and it's the kind of name that's
narrower or newer than, say, Python, JavaScript, GitHub, or React — add a
short (2–6 word) plain-language gloss the first time it appears in the item.
Don't turn the item into a tutorial; one clause is enough.

**Before** (assumes the reader already knows what Bun is):
> Bun runtime حالا از Bun.serve() به‌عنوان ورودی‌کد پشتیبانی می‌کنه.

**After** (same fact, one clause of context added):
> Bun، یک جایگزین سریع برای Node.js، حالا از Bun.serve() به‌عنوان ورودی‌کد پشتیبانی می‌کنه.

This isn't about dumbing content down for experienced readers — a senior
engineer skims past a clause they already know in under a second, but a
junior reader who hits an unexplained name either stalls or silently stops
understanding the rest of the item. A short gloss costs the expert reader
almost nothing and saves the beginner reader the whole item.
