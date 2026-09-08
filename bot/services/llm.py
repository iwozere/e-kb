"""Claude API wrapper with prompt caching support.

Replaces the previous Gemini-based llm.py.  All AI calls now go through the
Anthropic SDK using claude-sonnet-4-6.

Prompt caching:
  Pass cache_system=True to mark the system prompt as ephemeral-cacheable.
  Useful when the same system prompt is repeated across many calls (e.g. /ask,
  /draft where the user profile is static). Anthropic caches it for ~5 minutes,
  cutting input-token costs ~60-70 % on warm hits.
"""
import logging
from typing import Union

import anthropic

from bot.utils.config import settings

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"

_client: anthropic.AsyncAnthropic | None = None


class LLMUsageError(Exception):
    """Raised when a Claude API call fails for an account-level reason —
    out of credits, a bad/revoked API key, or a rate limit — rather than a
    transient network hiccup or a parsing error.

    Callers that currently swallow LLM failures with a generic fallback
    (classifier.py, etc.) should let this specific error propagate so the
    user/admin can be warned with a clear, actionable message instead of a
    silent degrade or a generic "something went wrong".
    """


# BadRequestError (400) is also used for ordinary malformed-request cases,
# so only treat it as a usage error when the message says so.
_BILLING_KEYWORDS = ("credit balance", "billing", "insufficient credit")


def _usage_error_reason(exc: Exception) -> str | None:
    """Return a short human-readable reason if ``exc`` is an account/usage
    failure, else None."""
    if isinstance(exc, anthropic.AuthenticationError):
        return "invalid or revoked API key"
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "API key lacks permission"
    if isinstance(exc, anthropic.RateLimitError):
        return "rate limited / quota exceeded"
    if isinstance(exc, anthropic.BadRequestError):
        message = str(exc).lower()
        if any(kw in message for kw in _BILLING_KEYWORDS):
            return "out of API credits"
    return None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


def _build_system(text: str, cache: bool) -> Union[str, list]:
    if cache:
        return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
    return text


async def _create_message(*, max_tokens: int, system, messages: list, effort: str):
    """Shared call site for messages.create(). Translates account/usage-level
    API errors into LLMUsageError so callers can distinguish them from
    transient or parsing failures; other errors propagate unchanged."""
    try:
        return await _get_client().messages.create(
            model=MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
            output_config={"effort": effort},
        )
    except anthropic.APIStatusError as e:
        reason = _usage_error_reason(e)
        if reason:
            raise LLMUsageError(reason) from e
        raise


async def complete(
    system: str,
    user: str,
    max_tokens: int = 1000,
    cache_system: bool = False,
    effort: str = "low",
) -> str:
    """Single-turn completion with optional system-prompt caching.

    ``effort`` defaults to "low" — most callers are classification, title
    generation, /log parsing, or digest summarization, which don't need deep
    reasoning. Pass "medium"/"high" at the call site for tasks that do (e.g.
    /draft's style_engine.py).

    Raises ``LLMUsageError`` (instead of the raw SDK exception) when the
    call fails for an account-level reason — out of credits, bad API key,
    rate limit — so callers can show a distinct warning.
    """
    response = await _create_message(
        max_tokens=max_tokens,
        system=_build_system(system, cache_system),
        messages=[{"role": "user", "content": user}],
        effort=effort,
    )
    return response.content[0].text


async def complete_with_history(
    system: str,
    history: list[dict],
    user: str,
    max_tokens: int = 1500,
    cache_system: bool = True,
    effort: str = "medium",
) -> str:
    """
    Multi-turn completion with conversation history.

    Put the STATIC part of your prompt in ``system`` (user profile, persona).
    Put DYNAMIC context (search results) in the ``user`` message so the system
    prompt remains identical across calls and caching stays effective.

    ``effort`` defaults to "medium" — used only by /ask, which needs more
    reasoning than the single-turn classification/parsing calls.

    Raises ``LLMUsageError`` (instead of the raw SDK exception) when the
    call fails for an account-level reason — out of credits, bad API key,
    rate limit — so callers can show a distinct warning.
    """
    messages = list(history) + [{"role": "user", "content": user}]
    response = await _create_message(
        max_tokens=max_tokens,
        system=_build_system(system, cache_system),
        messages=messages,
        effort=effort,
    )
    return response.content[0].text
