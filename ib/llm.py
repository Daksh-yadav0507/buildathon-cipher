"""The one AI call (section 8.1): an OpenAI-compatible /chat/completions endpoint set in .env.

Nothing else in the app talks to the AI. With no AI_BASE_URL (or IB_NO_AI=1) configured() is False and the
callers (ask, brief, keyq) fall back to code-only answers that still cite records.
"""
from __future__ import annotations

import json
import re
import sys

import httpx

from ib import config

# records holding a saved password or OTP never go to the AI
_SECRET_RE = re.compile(r"\b(otp|password|pin)\b.*\d{4,}", re.IGNORECASE | re.DOTALL)

CODE_ONLY_LINE = "Answered by code only: no AI is set up on this computer."


class LLMError(Exception):
    """The AI could not be reached or gave nothing usable. The message is a plain sentence."""


def settings() -> config.AISettings:
    return config.ai()


def configured() -> bool:
    return settings().configured


def where() -> str:
    """'on this computer' or 'at <host>'."""
    return settings().where


def status_line() -> str:
    """The line under the Ask box."""
    s = settings()
    if not s.configured:
        return CODE_ONLY_LINE
    return "The AI runs on this computer" if s.local else f"The AI runs at {s.host}"


def is_secret(body: str | None) -> bool:
    """True for a record that looks like it holds a password, PIN or OTP: it must not be sent to the AI."""
    return bool(body) and bool(_SECRET_RE.search(body))


def chat(messages: list[dict], max_tokens: int | None = None, temperature: float = 0.2) -> tuple[str, str]:
    """One call. Returns (reply text, finish_reason). Raises LLMError with a plain sentence."""
    s = settings()
    if not s.configured:
        raise LLMError("No AI is set up on this computer.")
    payload = {"model": s.model or "local-model", "messages": messages, "temperature": temperature,
               "max_tokens": int(max_tokens or s.max_tokens)}
    headers = {"Content-Type": "application/json"}
    if s.api_key:
        headers["Authorization"] = f"Bearer {s.api_key}"
    try:
        with httpx.Client(timeout=s.timeout_s) as client:
            r = client.post(s.chat_url, json=payload, headers=headers)
    except httpx.TimeoutException as e:
        raise LLMError(f"The AI {s.where} took too long to answer.") from e
    except httpx.HTTPError as e:
        raise LLMError(f"The AI {s.where} could not be reached.") from e
    if r.status_code >= 400:
        print(f"[llm] HTTP {r.status_code}: {r.text[:300]}", file=sys.stderr)
        raise LLMError(f"The AI {s.where} refused the request.")
    try:
        data = r.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or choice.get("text") or ""
        finish = choice.get("finish_reason") or ""
    except (ValueError, AttributeError, IndexError) as e:
        raise LLMError(f"The AI {s.where} gave a reply that could not be read.") from e
    # some local models think out loud first
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content, str(finish)


def parse_json(reply: str | None):
    """The text between the first '{' and the last '}', parsed; None if that fails."""
    if not reply:
        return None
    a, b = reply.find("{"), reply.rfind("}")
    if a < 0 or b <= a:
        return None
    try:
        out = json.loads(reply[a:b + 1])
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def ask_json(system: str, user: str, max_tokens: int | None = None) -> tuple[dict | None, str]:
    """Ask for JSON; retry once with 'Reply with JSON only.' Returns (parsed or None, finish_reason).

    finish_reason == 'length' means the reply was cut off: the caller must not resend the same thing
    (it halves the evidence instead).
    """
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    reply, finish = chat(messages, max_tokens)
    out = parse_json(reply)
    if out is not None or finish == "length":
        return out, finish
    messages += [{"role": "assistant", "content": reply or ""}, {"role": "user", "content": "Reply with JSON only."}]
    reply, finish = chat(messages, max_tokens)
    return parse_json(reply), finish
