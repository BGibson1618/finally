"""Tests for the mock LLM caller (LLM_MOCK=true path)."""

from __future__ import annotations

import pytest

from app.chat.llm import call_llm_mock
from app.chat.models import LlmResponse


async def test_mock_generic_message_echoes() -> None:
    resp = await call_llm_mock(
        user_message="hello",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": []},
        history=[],
    )
    assert isinstance(resp, LlmResponse)
    assert "hello" in resp.message.lower() or resp.message
    assert resp.trades == []
    assert resp.watchlist_changes == []


async def test_mock_buy_instruction_produces_trade() -> None:
    resp = await call_llm_mock(
        user_message="buy 5 AAPL",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": ["AAPL"]},
        history=[],
    )
    assert len(resp.trades) == 1
    t = resp.trades[0]
    assert t.ticker == "AAPL"
    assert t.side == "buy"
    assert t.quantity == pytest.approx(5.0)


async def test_mock_sell_instruction_produces_trade() -> None:
    resp = await call_llm_mock(
        user_message="sell 3 TSLA",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": ["TSLA"]},
        history=[],
    )
    assert len(resp.trades) == 1
    assert resp.trades[0].side == "sell"
    assert resp.trades[0].ticker == "TSLA"


async def test_mock_add_watchlist_instruction() -> None:
    resp = await call_llm_mock(
        user_message="add PYPL to my watchlist",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": []},
        history=[],
    )
    assert len(resp.watchlist_changes) == 1
    assert resp.watchlist_changes[0].ticker == "PYPL"
    assert resp.watchlist_changes[0].action == "add"


async def test_mock_remove_watchlist_instruction() -> None:
    resp = await call_llm_mock(
        user_message="remove AAPL from watchlist",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": ["AAPL"]},
        history=[],
    )
    assert len(resp.watchlist_changes) == 1
    assert resp.watchlist_changes[0].ticker == "AAPL"
    assert resp.watchlist_changes[0].action == "remove"
