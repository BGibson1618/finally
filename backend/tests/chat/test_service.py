"""Tests for chat service orchestration: propose → confirm → execute."""

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


@pytest.fixture
def chat_service(monkeypatch: pytest.MonkeyPatch):
    """Chat service wired up with LLM_MOCK=true and a fresh settings cache."""
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service
    return service


async def test_generic_message_has_no_actions(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    resp = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "hello"
    )
    assert resp.proposed_actions == []
    assert resp.executed_actions == []
    rows = await db.fetchall("SELECT role FROM chat_messages ORDER BY created_at")
    assert [r["role"] for r in rows] == ["user", "assistant"]


async def test_trade_request_proposes_but_does_not_execute(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    resp = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 2 AAPL"
    )
    # Proposed, not executed
    assert resp.executed_actions == []
    assert len(resp.proposed_actions) == 1
    p = resp.proposed_actions[0]
    assert p.kind == "trade"
    assert p.ticker == "AAPL"
    assert p.side == "buy"
    assert p.quantity == 2.0

    # Portfolio is untouched until confirmation
    state = await portfolio_service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions == []
    assert state.cash_balance == 10_000.0


async def test_confirm_executes_proposed_trade(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    r1 = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 2 AAPL"
    )
    r2 = await chat_service.handle_user_message(
        db,
        price_cache,
        source,
        DEFAULT_USER_ID,
        "yes, confirm",
        confirm_actions=r1.proposed_actions,
    )
    assert any(
        a.kind == "trade" and a.status == "ok" for a in r2.executed_actions
    )
    state = await portfolio_service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions[0].ticker == "AAPL"
    assert state.positions[0].quantity == 2.0


async def test_cancel_is_just_a_new_message(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    """Sending a new message without confirm_actions implicitly cancels."""
    await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 2 AAPL"
    )
    resp = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "actually nevermind"
    )
    assert resp.executed_actions == []
    state = await portfolio_service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions == []


async def test_confirm_reports_error_for_failed_trade(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    r1 = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 1000 NVDA"
    )
    r2 = await chat_service.handle_user_message(
        db,
        price_cache,
        source,
        DEFAULT_USER_ID,
        "confirm",
        confirm_actions=r1.proposed_actions,
    )
    assert any(
        a.kind == "trade" and a.status == "error" for a in r2.executed_actions
    )


async def test_watchlist_add_requires_confirmation(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    r1 = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "add PYPL to my watchlist"
    )
    assert len(r1.proposed_actions) == 1
    assert r1.proposed_actions[0].kind == "watchlist_add"
    assert r1.proposed_actions[0].ticker == "PYPL"
    assert source.added == []  # not yet added

    r2 = await chat_service.handle_user_message(
        db,
        price_cache,
        source,
        DEFAULT_USER_ID,
        "confirm",
        confirm_actions=r1.proposed_actions,
    )
    assert any(
        a.kind == "watchlist_add" and a.status == "ok" for a in r2.executed_actions
    )
    assert "PYPL" in source.added


async def test_confirm_persists_executed_actions_json(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    r1 = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 1 AAPL"
    )
    await chat_service.handle_user_message(
        db,
        price_cache,
        source,
        DEFAULT_USER_ID,
        "confirm",
        confirm_actions=r1.proposed_actions,
    )
    row = await db.fetchone(
        "SELECT actions FROM chat_messages WHERE role='assistant' "
        "ORDER BY created_at DESC LIMIT 1"
    )
    parsed = json.loads(row["actions"])
    assert isinstance(parsed, list)
    assert any(a["kind"] == "trade" for a in parsed)


async def test_llm_failure_does_not_orphan_user_message(
    db: Database, price_cache: PriceCache, source: _StubSource,
    chat_service, monkeypatch,
) -> None:
    """If the LLM call raises, no chat_messages row should exist."""
    from app.chat import llm

    async def boom(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr(llm, "call_llm_mock", boom)

    with pytest.raises(RuntimeError):
        await chat_service.handle_user_message(
            db, price_cache, source, DEFAULT_USER_ID, "hello"
        )

    rows = await db.fetchall("SELECT role, content FROM chat_messages")
    assert rows == []


async def test_confirm_ignores_llm_even_if_it_would_suggest(
    db: Database, price_cache: PriceCache, source: _StubSource, chat_service
) -> None:
    """A confirm turn must not trigger the LLM (saves cost, avoids surprises)."""
    from app.chat import llm

    called = {"n": 0}
    orig = llm.call_llm_mock

    async def counting_mock(*args, **kwargs):
        called["n"] += 1
        return await orig(*args, **kwargs)

    # Propose first (LLM will be called once here)
    r1 = await chat_service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 1 AAPL"
    )
    assert called["n"] == 0  # not patched yet — sanity

    # Patch before the confirm turn
    llm.call_llm_mock = counting_mock
    try:
        await chat_service.handle_user_message(
            db,
            price_cache,
            source,
            DEFAULT_USER_ID,
            "confirm",
            confirm_actions=r1.proposed_actions,
        )
    finally:
        llm.call_llm_mock = orig
    assert called["n"] == 0
