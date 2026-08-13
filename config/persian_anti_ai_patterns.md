<!--
Companion to register.md, not a replacement for it. register.md sets the
register (colloquial vs. literary); this file catalogs the specific words,
sentence habits, and typographic tells that make Persian tech writing read
as AI-generated, so the draft prompt and the style self-check pass both know
what to watch for.

Why this exists as a separate file instead of reusing an English list:
most of Wikipedia's "Signs of AI writing" guide (the source the `humanizer`
skill is built on, and the general inspiration for this document) is a list
of specific English words - "testament," "delve," "underscore," "vibrant
tapestry." None of that transfers to Persian by translation; Persian
AI-generated text has its own stock vocabulary, and literal translation of
the English tell-words would just produce a different set of false
positives. A handful of patterns (dashes, curly quotes, boldface/emoji
overuse, rule-of-three) are about structure rather than specific words, so
those do transfer directly and are included as-is.

src/write_llm.py loads this as a raw string, same as register.md - it goes
into both the drafting prompt and the style self-check prompt.
-->

# Persian anti-AI-writing patterns

This is authored content, not a placeholder - written for this project by
adapting the `humanizer` skill's pattern taxonomy to Persian. If the channel
develops its own sense of what reads as AI-generated (readers say a
particular phrase "sounds like ChatGPT," or a pattern keeps slipping
through), add it here; this file is meant to grow the same way
`register.md`'s glossary does.

## 1. Translationese sentence structure (the biggest one)

This is covered in register.md's "avoid word-for-word sentence structures"
line; it's worth restating in full here because it causes more of the
"this sounds like AI" reaction than any single word choice does.

The method:
1. Read the source sentence for its meaning, not its words.
2. Forget the sentence was in English.
3. Rebuild it the way a Persian-speaking developer would say it from
   scratch, with Persian sentence order (verb position, clause order),
   not English order with Persian words substituted in.
4. Read the result out loud (in your head) and ask: would a Persian
   speaker need to pause and re-parse this, or is it immediate? If it
   needs a second pass, rewrite it.

**Before (English structure, Persian words):**
> این ویژگی جدید که توسط تیم توسعه‌دهنده به‌طور خاص برای بهبود عملکرد در پروژه‌های بزرگ طراحی شده است، اکنون در دسترس قرار گرفته است.

**After (rebuilt in Persian order):**
> این قابلیت تازه برای پروژه‌های بزرگ طراحی شده و حالا در دسترسه.

## 2. Persian AI-cliché vocabulary and phrases

The Persian-language equivalent of Wikipedia's "AI vocabulary" list - words
and short phrases that show up far more in AI output than in how a person
actually writes about a release or a tool. State the concrete fact instead.

**Watch for:** نقش بسزایی/مهمی/کلیدی ایفا می‌کند، در دنیای امروز (فناوری)،
گامی مهم/بزرگ در راستای، بدون شک، شکی نیست که، تجربه‌ای بی‌نظیر/منحصربه‌فرد،
دنیای [برنامه‌نویسی/فناوری] را متحول خواهد کرد، پتانسیل بالایی دارد، چشم‌انداز
روشنی، آینده‌ی روشنی در انتظار است، باید منتظر ماند و دید، نویدبخش، سنگ بنای،
نقطه عطف، بستری فراهم کرده است.

**Before:**
> این آپدیت نقش بسزایی در بهبود عملکرد ایفا می‌کند و می‌تواند دنیای توسعه‌ی وب را متحول کند.

**After:**
> این آپدیت زمان build رو حدود ۴۰ درصد کاهش می‌ده.

(The specific number has to come from the source. If the source doesn't
give one, say what changed without the inflated claim: "این آپدیت سرعت
build رو بالا می‌بره.")

## 3. Significance inflation

Same failure mode as #2 but at the paragraph level: framing a routine
release or a minor fix as historic. A point release is a point release.

**Before:**
> نسخه‌ی ۲.۳ این کتابخانه منتشر شد؛ رویدادی که نشان‌دهنده‌ی تعهد تیم توسعه به نوآوری مستمر و بهبود مداوم تجربه‌ی توسعه‌دهندگان است.

**After:**
> نسخه‌ی ۲.۳ این کتابخانه منتشر شد؛ یک باگ قدیمی در type inference رفع شده و سرعت build کمی بهتر شده.

## 4. Avoiding the plain copula (است/هست) with elaborate substitutes

The Persian analog of "boasts/serves as/features" instead of "is." Not every
"محسوب می‌شود" or "به شمار می‌رود" is AI-written - these are legitimate
literary constructions - but stacking them where a plain "است" would do is
a tell, especially next to a simple factual claim.

**Before:**
> این ابزار به‌عنوان یکی از سریع‌ترین bundlerهای موجود به شمار می‌رود و دارای پشتیبانی کامل از TypeScript محسوب می‌شود.

**After:**
> این ابزار یکی از سریع‌ترین bundlerهاست و از TypeScript هم کامل پشتیبانی می‌کنه.

## 5. Forced rule-of-three and false ranges

LLMs pad lists to exactly three items to sound thorough, and reach for
"از X تا Y" constructions where X and Y aren't actually two ends of a real
scale. Use however many items the source actually supports, and only use
"از ... تا ..." when there's a real range.

**Before:**
> این نسخه سریع‌تر، ساده‌تر و کارآمدتر شده و از رابط کاربری تا مستندات، از عملکرد تا امنیت، همه‌چیز رو پوشش می‌ده.

**After:**
> این نسخه سریع‌تر شده و مستندات هم به‌روزرسانی شده.

## 6. Superficial padding clauses

Persian equivalent of the English "-ing" padding tell ("...showcasing...",
"...reflecting..."): a clause tacked onto the end of a sentence that
restates it in fancier words instead of adding information. "که
نشان‌دهنده‌ی..." / "که بیانگر..." / "که گواهی است بر..." are the usual
shapes.

**Before:**
> تیم Vue.js یک RFC جدید منتشر کرد که نشان‌دهنده‌ی تعهد این پروژه به بهبود مستمر تجربه‌ی توسعه‌دهندگان است.

**After:**
> تیم Vue.js یک RFC جدید منتشر کرد؛ این پیشنهاد نحوه‌ی تعریف component propها رو ساده‌تر می‌کنه.

## 7. Signposting and meta-commentary

An item is a finished 3-5 sentence brief, not a tutorial - it should never
announce what it's about to do or talk to the reader directly.

**Watch for:** بیایید نگاهی بیندازیم به، در این بخش به بررسی می‌پردازیم،
در ادامه خواهیم دید، امیدوارم این خبر براتون مفید باشه، با ما همراه باشید،
اگر سوالی داشتید بگید.

**Before:**
> بیایید نگاهی بندازیم به آخرین آپدیت React. در این پست به بررسی تغییرات جدید می‌پردازیم.

**After:**
> React 19.2 با یک compiler جدید عرضه شد که re-renderهای غیرضروری رو خودکار حذف می‌کنه.

## 8. Generic, vague endings

Don't close an item on an unsupported forward-looking claim. End on the
last concrete fact from the source.

**Before:**
> باید دید این تغییر چه تاثیری روی اکوسیستم خواهد گذاشت؛ آینده‌ی نویدبخشی در انتظار این پروژه است.

**After:**
> (Cut the sentence. End the item on whatever the source actually confirms,
> e.g. "نسخه‌ی پایدار قراره ماه آینده منتشر بشه" - only if the source says so.)

## 9. Typographic tells that transfer directly from English

These aren't about word choice, so they carry over from the general
anti-AI-writing guidance without translation:

- **Em/en dash (— / –) and spaced double-hyphens ( -- ).** Persian prose
  rarely uses these; when they show up in Persian AI output it's almost
  always a leftover habit from the English text the model was drafting
  from. Replace with a comma, a period, or a colon depending on what the
  dash was doing - restructure the sentence rather than just swapping the
  character.
- **Curly quotes (“ ”)** instead of straight quotes ("") or Persian
  guillemets (« »). Pick whichever the channel already uses and be
  consistent; the curly ones are the ChatGPT-default tell, not a style
  choice.
- **Boldface on ordinary phrases**, the way AI chatbots bold nearly every
  noun phrase in a list. Bold only what genuinely needs emphasis, per
  telegram_formatting.md.
- **An emoji on every sentence.** The channel's existing voice uses emoji
  sparingly and specifically (see telegram_formatting.md and how the
  channel has used them before) - not one per line as a decoration habit.

## What NOT to flag (false positives)

Don't over-correct. The following are not reliable signals on their own:

- **Established technical vocabulary in Latin script** (API, SDK, runtime,
  build, deploy) - that's register.md's glossary rule, not an AI tell.
- **A single formal-sounding word in isolation** - "کلیدی" or "مهم" used
  once is just a word. It's the cluster (several patterns from this list
  together) that signals AI writing, not one instance of one pattern.
- **Persian guillemets (« »)** used for an actual quotation - that's
  correct Persian typography, not a tell. Curly English-style quotes are
  the actual problem, not quotation marks in general.
- **A short, direct sentence.** Brevity isn't a tell; the padding clauses
  and inflated framing above are.

## Self-check question

Before finishing a self-check pass, ask directly: "اگر یک برنامه‌نویس
فارسی‌زبان که هر روز همین کانال رو می‌خونه این متن رو ببینه، چیزی توش حس
ترجمه‌ای، کلیشه‌ای یا تبلیغاتی بهش دست می‌ده؟" If yes, rewrite the specific
part that triggered it rather than the whole item - see the no-fabrication
and information-preservation rules in register.md, which still apply here:
fixing the phrasing must never add or remove a fact.
