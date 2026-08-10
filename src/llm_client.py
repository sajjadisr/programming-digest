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
  GEMINI_MODEL     - optional, defaults to "gemini-flash-latest"
  GROQ_MODEL       - optional, defaults to "llama-3.3-70b-versatile"
"""
from __future__ import annotations

import json
import os
import re

from google import genai
from google.genai import types as genai_types
from groq import Groq

_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
_GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

_gemini_client: genai.Client | None = None
_groq_client: Groq | None = None


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


def _complete_gemini(system: str, user: str, max_tokens: int) -> str:
    client = _get_gemini_client()
    resp = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=user,
        config=genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens,
        ),
    )
    text = resp.text
    if not text:
        # Empty is usually a safety block or a finish_reason=MAX_TOKENS cutoff
        # before any text was produced - treat it as a failure so the caller
        # falls back to Groq rather than choking on an empty string.
        raise RuntimeError(f"Gemini returned no text (finish_reason={resp.candidates[0].finish_reason if resp.candidates else 'unknown'})")
    return text


def _complete_groq(system: str, user: str, max_tokens: int) -> str:
    client = _get_groq_client()
    resp = client.chat.completions.create(
        model=_GROQ_MODEL,
        max_completion_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def complete(system: str, user: str, max_tokens: int = 4096) -> str:
    """One-shot completion, returns the raw text response.

    Tries Gemini first; falls back to Groq only if Gemini raises. Any Groq
    failure after that is real - raised so the caller (and the GitHub
    Actions log) sees it rather than the run silently producing nothing.
    """
    try:
        return _complete_gemini(system, user, max_tokens)
    except Exception as gemini_err:
        print(f"[llm_client] Gemini call failed ({gemini_err!r}), falling back to Groq")
        try:
            return _complete_groq(system, user, max_tokens)
        except Exception as groq_err:
            raise RuntimeError(
                f"Both LLM providers failed. Gemini: {gemini_err!r}. Groq: {groq_err!r}"
            ) from groq_err


def complete_json(system: str, user: str, max_tokens: int = 4096) -> dict:
    """Completion where the system prompt has instructed strict-JSON-only output.

    Strips markdown code fences defensively in case the model wraps its answer
    anyway, then parses. Raises with the raw text attached if parsing fails so
    the caller can log/debug rather than silently losing the day's run.
    """
    raw = complete(system, user, max_tokens=max_tokens)
    cleaned = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM did not return valid JSON: {e}\n---raw---\n{raw}") from e
