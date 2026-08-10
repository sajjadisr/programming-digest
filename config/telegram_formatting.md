<!--
PLACEHOLDER — same situation as register.md: the review references a
`TELEGRAM_FORMATTING` string meant to be reused verbatim. Replace this file's
content with your real one if you have it; src/deliver.py and src/write.py
both load it as a raw string.
-->

# Telegram formatting rules (draft — replace with your real one if you have it)

- Use Telegram's MarkdownV2 subset: `*bold*` for the item's title line, plain
  text for the body, `[متن لینک](url)` for the source link.
- Every option message ends with a source link line, no exceptions — this is
  the non-negotiable safety net for factual grounding.
- Escape MarkdownV2 special characters (`_ * [ ] ( ) ~ \` > # + - = | { } . !`)
  in any text pulled from an external source (titles, quotes) before sending.
- No more than one blank line between sections of a message.
- Date header format for the first message of the day: `📅 <روز، تاریخ>`.
