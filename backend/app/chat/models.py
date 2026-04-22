"""Pydantic models for chat requests and LLM structured output."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.portfolio.models import TICKER_PATTERN


class ProposedTrade(BaseModel):
    kind: Literal["trade"] = "trade"
    ticker: str = Field(min_length=1, max_length=6, pattern=TICKER_PATTERN)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class ProposedWatchlistChange(BaseModel):
    kind: Literal["watchlist_add", "watchlist_remove"]
    ticker: str = Field(min_length=1, max_length=6, pattern=TICKER_PATTERN)


ProposedAction = Annotated[
    Union[ProposedTrade, ProposedWatchlistChange],
    Field(discriminator="kind"),
]


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    # When present, the server executes these actions instead of calling the LLM.
    # Used for two-turn confirmation: the client sends back the proposed_actions
    # it received on the prior turn.
    confirm_actions: list[ProposedAction] | None = None


class LlmTrade(BaseModel):
    ticker: str = Field(min_length=1, max_length=6, pattern=TICKER_PATTERN)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class LlmWatchlistChange(BaseModel):
    ticker: str = Field(min_length=1, max_length=6, pattern=TICKER_PATTERN)
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
    # Actions the LLM suggested but did NOT execute. The client presents these
    # for confirmation and sends them back in `confirm_actions` on the next turn.
    proposed_actions: list[ProposedAction] = Field(default_factory=list)
    # Actions that actually ran, either because the user confirmed a prior
    # proposal or (in the future) some non-LLM endpoint executed them.
    executed_actions: list[ExecutedAction] = Field(default_factory=list)
