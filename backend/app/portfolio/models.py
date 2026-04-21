"""Pydantic response models for portfolio endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Position(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    market_value: float | None
    unrealized_pl: float | None
    unrealized_pl_percent: float | None


class PortfolioState(BaseModel):
    cash_balance: float
    total_value: float
    positions_value: float
    unrealized_pl: float
    positions: list[Position]


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class TradeResult(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    executed_at: str


class Snapshot(BaseModel):
    total_value: float
    recorded_at: str
