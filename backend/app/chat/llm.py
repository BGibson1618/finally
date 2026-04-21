"""LLM client: real mode via LiteLLM+OpenRouter+Cerebras, plus deterministic mock mode."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import litellm

from app.chat.models import LlmResponse, LlmTrade, LlmWatchlistChange

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant embedded in a simulated portfolio workstation.
You can analyze the user's positions, suggest trades, and execute trades and watchlist changes on their behalf.

Rules:
- Respond ONLY with a JSON object that matches the schema provided.
- The "message" field is required and holds your conversational reply.
- Populate "trades" only when the user explicitly asks you to trade or agrees to a suggestion.
- Populate "watchlist_changes" only when the user asks to add/remove a ticker.
- Be concise, data-driven, and ground every suggestion in the portfolio context provided."""


async def call_llm(
    user_message: str,
    portfolio_context: dict[str, Any],
    history: list[dict[str, str]],
    api_key: str,
) -> LlmResponse:
    """Call the LLM via LiteLLM/OpenRouter/Cerebras with structured output."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"PORTFOLIO CONTEXT:\n{json.dumps(portfolio_context, indent=2)}",
        },
        *history,
        {"role": "user", "content": user_message},
    ]

    completion = await litellm.acompletion(
        model=MODEL,
        messages=messages,
        api_key=api_key,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "ChatResponse",
                "strict": True,
                "schema": LlmResponse.model_json_schema(),
            },
        },
        extra_body={"provider": {"order": ["Cerebras"]}},
    )
    raw = completion.choices[0].message.content or "{}"
    return LlmResponse.model_validate_json(raw)


# --- Deterministic mock for LLM_MOCK=true ----------------------------------

_BUY_RE = re.compile(r"\bbuy\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,6})\b", re.IGNORECASE)
_SELL_RE = re.compile(r"\bsell\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,6})\b", re.IGNORECASE)
_ADD_RE = re.compile(r"\badd\s+([A-Za-z]{1,6})\b.*?\bwatch", re.IGNORECASE | re.DOTALL)
_REMOVE_RE = re.compile(
    r"\bremove\s+([A-Za-z]{1,6})\b.*?\bwatch", re.IGNORECASE | re.DOTALL
)


async def call_llm_mock(
    user_message: str,
    portfolio_context: dict[str, Any],
    history: list[dict[str, str]],
) -> LlmResponse:
    """Deterministic mock for testing. Parses simple instructions from the message."""
    trades: list[LlmTrade] = []
    changes: list[LlmWatchlistChange] = []

    for qty, ticker in _BUY_RE.findall(user_message):
        trades.append(LlmTrade(ticker=ticker.upper(), side="buy", quantity=float(qty)))
    for qty, ticker in _SELL_RE.findall(user_message):
        trades.append(LlmTrade(ticker=ticker.upper(), side="sell", quantity=float(qty)))
    for ticker in _ADD_RE.findall(user_message):
        changes.append(LlmWatchlistChange(ticker=ticker.upper(), action="add"))
    for ticker in _REMOVE_RE.findall(user_message):
        changes.append(LlmWatchlistChange(ticker=ticker.upper(), action="remove"))

    if trades or changes:
        reply = f"Acknowledged: {user_message.strip()}"
    else:
        reply = f"[MOCK] You said: {user_message.strip()}"

    return LlmResponse(message=reply, trades=trades, watchlist_changes=changes)
