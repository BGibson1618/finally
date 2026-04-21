"""Tests for chat service orchestration: context + execute + persist."""

from __future__ import annotations

import json

import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.market import PriceCache
from app.portfolio import service as portfolio_service


class _StubSource:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)


@pytest.fixture
def source() -> _StubSource:
    return _StubSource()


async def test_handle_user_message_stores_both_turns(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    await service.handle_user_message(db, price_cache, source, DEFAULT_USER_ID, "hello")
    rows = await db.fetchall(
        "SELECT role, content FROM chat_messages ORDER BY created_at"
    )
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "hello"


async def test_handle_user_message_executes_trade(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    resp = await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 2 AAPL"
    )
    assert any(a.kind == "trade" and a.status == "ok" for a in resp.executed_actions)
    state = await portfolio_service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions[0].ticker == "AAPL"
    assert state.positions[0].quantity == 2.0


async def test_handle_user_message_failed_trade_reports_error(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    resp = await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 1000 NVDA"
    )
    assert any(a.kind == "trade" and a.status == "error" for a in resp.executed_actions)


async def test_handle_user_message_adds_watchlist(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    resp = await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "add PYPL to my watchlist"
    )
    assert any(a.kind == "watchlist_add" and a.status == "ok" for a in resp.executed_actions)
    assert "PYPL" in source.added


async def test_handle_user_message_persists_actions_json(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 1 AAPL"
    )
    row = await db.fetchone(
        "SELECT actions FROM chat_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1"
    )
    parsed = json.loads(row["actions"])
    assert isinstance(parsed, list)
    assert any(a["kind"] == "trade" for a in parsed)
