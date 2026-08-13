"""Thin wrapper around free-tier LLM APIs (Gemini primary, Groq fallback).

Both select_llm.py and write_llm.py go through here so there's one place to
change providers, models, or fallback behavior.

Why two providers: this pipeline runs unattended once a day via GitHub
Actions (propose.yml). Free tiers come with no uptime guarantee - a
rate-limit blip or a slow minute right when the workflow fires would
otherwise mean that day's digest silently never happens. Gemini is primary
because it's the stronger choice for the Persian writing/register/fact
self-checks in write_llm.py; Groq is a pure safety net that only gets used
if the Gemini call raises (network error, rate limit, safety block, etc).
It's not round-robin and not split-by-stage, so there's no ongoing
complexity - just a fallback.

Env vars:
  GEMINI_API_KEY   - required. Free key: https://aistudio.google.com/apikey
  GROQ_API_KEY     - required. Free key: https://console.groq.com/keys
  GEMINI_MODEL     - optional, defaults to "gemini-3.6-flash"
  GROQ_MODEL       - optional, defaults to "openai/gpt-oss-120b"

Both defaults are pinned to explicit, stable model IDs on purpose - do not
change either back to a "-latest"/floating alias. Two production breaks in
a row traced back to that:
  - "gemini-flash-latest" isn't a stable-channel alias; Google's own docs
    say it points at an experimental model not intended for production,
    with tighter rate limits, and it can silently repoint to a new model
    family (that's what broke thinking_budget on 2026-08-12).
  - "llama-3.3-70b-versatile" (the old Groq default) was deprecated
    2026-06-17 with a shutdown date of 2026-08-16 - Groq's own recommended
    replacement is openai/gpt-oss-120b, used here.
Pinned IDs still eventually get deprecated, but on an announced schedule
with weeks of notice - check https://console.groq.com/docs/deprecations
and https://ai.google.dev/gemini-api/docs/changelog occasionally, rather
than finding out at 6am when the workflow fails.
"""
from __future__ import annotations

import json
import os
import re

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types
from groq import BadRequestError as GroqBadRequestError
from groq import Groq

_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
_GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

_gemini_client: genai.Client | None = None
_groq_client: Groq | None = None

# Set once we see a *daily*-quota RESOURCE_EXHAUSTED from Gemini. The free
# tier's per-day limit (as low as 20 requests/day - see the 2026-08-12
# incident) doesn't reset until Google's quota window rolls over, so every
# further Gemini call this process makes is guaranteed to fail the same way.
# Without this, a run with N worthy items still fires N wasted Gemini
# requests (each one first, before falling back to Groq), which does
# nothing but add latency and log noise once the day's quota is gone.
# Per-minute 429s are NOT covered by this - those are transient and worth
# retrying with fresh calls, since the per-minute window resets quickly.
_gemini_daily_quota_exhausted = False


def _get_gemini_client() -> genai.Client:
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _gemini_client


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _groq_client


def _generate(config_kwargs: dict, user: str):
    client = _get_gemini_client()
    resp = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=user,
        config=genai_types.GenerateContentConfig(**config_kwargs),
    )
    text = resp.text
    if not text:
        # Empty is usually a safety block or a finish_reason=MAX_TOKENS cutoff
        # before any text was produced - treat it as a failure so the caller
        # falls back to Groq rather than choking on an empty string.
        raise RuntimeError(f"Gemini returned no text (finish_reason={resp.candidates[0].finish_reason if resp.candidates else 'unknown'})")
    return text


def _is_daily_quota_error(e: genai_errors.ClientError) -> bool:
    # 429s come in two flavors here: per-minute (transient, worth retrying
    # fresh next call) and per-day (dead for the rest of the process). The
    # response body's quotaId says which - e.g. "...PerDay..." vs
    # "...PerMinute...". Checking the stringified details is a bit loose but
    # avoids hardcoding a specific quotaId string that's itself free to
    # change; the substring "PerDay" is the stable part.
    return e.code == 429 and "PerDay" in str(e.details)


def _complete_gemini(system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
    global _gemini_daily_quota_exhausted
    if _gemini_daily_quota_exhausted:
        raise RuntimeError(
            f"{_GEMINI_MODEL} daily quota already confirmed exhausted this run; "
            "not spending another request finding that out again"
        )

    config_kwargs: dict = {
        "system_instruction": system,
        "max_output_tokens": max_tokens,
    }
    if json_mode:
        # Without this, "return only JSON" is just a suggestion in the prompt -
        # the model is free to answer in prose instead (which is what caused
        # it to write out a plain numbered list rather than the requested
        # object). response_mime_type constrains decoding to valid JSON.
        config_kwargs["response_mime_type"] = "application/json"
        # Minimize thinking so the max_output_tokens budget goes to the
        # visible answer, not invisible reasoning tokens. Gemini 3.x (the
        # pinned default) uses thinking_level and cannot fully disable
        # thinking on Flash models - "minimal" is the closest equivalent.
        # Gemini 2.5.x instead uses the older thinking_budget=0. Since
        # GEMINI_MODEL is user-overridable, don't hardcode a model-name
        # check (that's exactly what silently broke last time a model
        # family shifted) - try the param that matches the pinned default,
        # then fall back live if the API rejects it.
        config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_level="minimal")
    try:
        return _generate(config_kwargs, user)
    except genai_errors.ClientError as e:
        if _is_daily_quota_error(e):
            _gemini_daily_quota_exhausted = True
            print(f"[llm_client] {_GEMINI_MODEL} daily quota exhausted ({e!r}); "
                  "skipping Gemini for the remainder of this run")
            raise
        # The thinking_config retry below exists for ONE specific failure: the
        # model/version rejecting the shape of thinking_config we guessed
        # (a plain 400 INVALID_ARGUMENT). It used to trigger on *any*
        # ClientError, including 429s - which meant every rate-limited call
        # fired 3 back-to-back requests at Gemini instead of 1, burning
        # per-minute quota faster and adding latency for no benefit (a 429
        # isn't fixed by changing thinking_config). Narrow it to 400s only;
        # anything else (429, 5xx, etc.) goes straight to the Groq fallback.
        if json_mode and "thinking_config" in config_kwargs and e.code == 400:
            print(f"[llm_client] {_GEMINI_MODEL} rejected thinking_level ({e!r}); retrying with thinking_budget=0")
            config_kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)
            try:
                return _generate(config_kwargs, user)
            except genai_errors.ClientError as e2:
                if _is_daily_quota_error(e2):
                    _gemini_daily_quota_exhausted = True
                    print(f"[llm_client] {_GEMINI_MODEL} daily quota exhausted ({e2!r}); "
                          "skipping Gemini for the remainder of this run")
                    raise
                if e2.code != 400:
                    raise
                print(f"[llm_client] {_GEMINI_MODEL} rejected thinking_budget too ({e2!r}); retrying with no thinking override")
                config_kwargs.pop("thinking_config", None)
                return _generate(config_kwargs, user)
        raise


def _complete_groq(system: str, user: str, max_tokens: int, json_mode: bool = False) -> str:
    client = _get_groq_client()
    kwargs: dict = {
        "model": _GROQ_MODEL,
        "max_completion_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
        # openai/gpt-oss-* models on Groq default to "medium" reasoning
        # effort, and that hidden reasoning counts against
        # max_completion_tokens - on the fact-check call (2026-08-12 13:41
        # run) it ate the entire 1024-token budget before any JSON came out
        # ("max completion tokens reached before generating a valid
        # document"). None of these calls (clustering, drafting, register/
        # fact self-checks) are the kind of multi-step task that benefits
        # from deep reasoning, so cap it at "low" to leave the budget for the
        # actual answer. reasoning_effort is only documented for qwen3/
        # gpt-oss models on Groq - if GROQ_MODEL is overridden to something
        # that rejects the param, drop it and retry once rather than failing
        # the whole call over a param that was just an optimization.
        kwargs["reasoning_effort"] = "low"
    try:
        resp = client.chat.completions.create(**kwargs)
    except GroqBadRequestError as e:
        if "reasoning_effort" not in kwargs:
            raise
        print(f"[llm_client] {_GROQ_MODEL} rejected reasoning_effort ({e!r}); retrying without it")
        kwargs.pop("reasoning_effort")
        resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def complete(system: str, user: str, max_tokens: int = 4096, json_mode: bool = False) -> str:
    """One-shot completion, returns the raw text response.

    Tries Gemini first; falls back to Groq only if Gemini raises. Any Groq
    failure after that is real - raised so the caller (and the GitHub
    Actions log) sees it rather than the run silently producing nothing.
    """
    try:
        return _complete_gemini(system, user, max_tokens, json_mode=json_mode)
    except Exception as gemini_err:
        print(f"[llm_client] Gemini call failed ({gemini_err!r}), falling back to Groq")
        try:
            return _complete_groq(system, user, max_tokens, json_mode=json_mode)
        except Exception as groq_err:
            raise RuntimeError(
                f"Both LLM providers failed. Gemini: {gemini_err!r}. Groq: {groq_err!r}"
            ) from groq_err


def _parse_json(raw: str) -> dict:
    # Defensive strip in case a model wraps its answer in fences anyway.
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def complete_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    """Completion where the system prompt has instructed strict-JSON-only output.

    Runs its own Gemini -> Groq fallback (rather than going through complete())
    so that an unparseable-but-"successful" Gemini response - not just a raised
    exception - also triggers the Groq fallback instead of killing the run.
    """
    try:
        raw = _complete_gemini(system, user, max_tokens, json_mode=True)
        return _parse_json(raw)
    except Exception as gemini_err:
        print(f"[llm_client] Gemini JSON call failed ({gemini_err!r}), falling back to Groq")
        try:
            raw = _complete_groq(system, user, max_tokens, json_mode=True)
            return _parse_json(raw)
        except Exception as groq_err:
            raise RuntimeError(
                f"Both LLM providers failed to produce valid JSON. Gemini: {gemini_err!r}. Groq: {groq_err!r}"
            ) from groq_err
