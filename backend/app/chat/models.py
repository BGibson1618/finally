"""Pydantic models for chat requests and LLM structured output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class LlmTrade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class LlmWatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class LlmResponse(BaseModel):
    """Structured output schema the LLM must produce."""

    message: str
    trades: list[LlmTrade] = Field(default_factory=list)
    watchlist_changes: list[LlmWatchlistChange] = Field(default_factory=list)


class ExecutedAction(BaseModel):
    """One row in the executed_actions payload returned to the frontend."""

    kind: Literal["trade", "watchlist_add", "watchlist_remove"]
    ticker: str
    status: Literal["ok", "error"]
    detail: str  # e.g. "bought 10 @ $190.00" or "insufficient cash"


class ChatResponse(BaseModel):
    message: str
    executed_actions: list[ExecutedAction]
