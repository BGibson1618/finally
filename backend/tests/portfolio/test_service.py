"""Tests for portfolio service: valuation + trade execution."""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.market import PriceCache
from app.portfolio import service


async def test_get_portfolio_starts_empty(db: Database, price_cache: PriceCache) -> None:
    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.cash_balance == 10_000.0
    assert state.total_value == 10_000.0
    assert state.positions == []


async def _insert_position(
    db: Database, ticker: str, qty: float, avg_cost: float
) -> None:
    import uuid
    from datetime import datetime, timezone

    await db.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, qty, avg_cost,
         datetime.now(timezone.utc).isoformat()),
    )


async def test_get_portfolio_with_positions(db: Database, price_cache: PriceCache) -> None:
    # AAPL seed price = 190.0 (from conftest)
    await _insert_position(db, "AAPL", 10.0, 180.0)
    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)

    assert len(state.positions) == 1
    pos = state.positions[0]
    assert pos.ticker == "AAPL"
    assert pos.quantity == 10.0
    assert pos.avg_cost == 180.0
    assert pos.current_price == 190.0
    assert pos.market_value == 1900.0
    assert pos.unrealized_pl == pytest.approx(100.0)
    assert pos.unrealized_pl_percent == pytest.approx(100.0 / 1800.0 * 100)

    assert state.positions_value == 1900.0
    assert state.total_value == 10_000.0 + 1900.0


async def test_position_without_price_has_none_valuation(db: Database) -> None:
    empty_cache = PriceCache()
    await _insert_position(db, "AAPL", 10.0, 180.0)
    state = await service.get_portfolio(db, empty_cache, DEFAULT_USER_ID)

    pos = state.positions[0]
    assert pos.current_price is None
    assert pos.market_value is None
    assert pos.unrealized_pl is None
    # Positions with no price contribute 0 to portfolio value
    assert state.total_value == 10_000.0


async def test_buy_creates_position(db: Database, price_cache: PriceCache) -> None:
    result = await service.execute_trade(
        db, price_cache, DEFAULT_USER_ID, ticker="AAPL", side="buy", quantity=5.0
    )
    assert result.ticker == "AAPL"
    assert result.side == "buy"
    assert result.price == 190.0
    assert result.quantity == 5.0

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.cash_balance == 10_000.0 - 190.0 * 5.0
    assert len(state.positions) == 1
    assert state.positions[0].quantity == 5.0
    assert state.positions[0].avg_cost == 190.0


async def test_buy_averages_cost_on_second_purchase(
    db: Database, price_cache: PriceCache
) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)
    # Mutate cache price before second buy
    price_cache.update("AAPL", 200.0)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    pos = state.positions[0]
    assert pos.quantity == 20.0
    # (10*190 + 10*200) / 20 = 195
    assert pos.avg_cost == pytest.approx(195.0)


async def test_buy_insufficient_cash_raises(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(service.InsufficientFundsError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "NVDA", "buy", 1000.0
        )


async def test_buy_unknown_ticker_raises(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(service.UnknownTickerError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "DOESNOTEXIST", "buy", 1.0
        )


async def test_sell_reduces_position(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 4.0)

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions[0].quantity == 6.0
    # Avg cost should not change on sell
    assert state.positions[0].avg_cost == 190.0
    assert state.cash_balance == 10_000.0 - 10*190.0 + 4*190.0


async def test_sell_entire_position_removes_row(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 10.0)

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions == []


async def test_sell_more_than_owned_raises(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 1.0)
    with pytest.raises(service.InsufficientSharesError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 2.0
        )


async def test_sell_no_position_raises(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(service.InsufficientSharesError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 1.0
        )


async def test_trade_writes_to_trades_table(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 3.0)
    rows = await db.fetchall("SELECT ticker, side, quantity, price FROM trades")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["side"] == "buy"
    assert rows[0]["quantity"] == 3.0
    assert rows[0]["price"] == 190.0


async def test_trade_quantity_must_be_positive(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(ValueError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 0.0
        )
    with pytest.raises(ValueError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", -1.0
        )


async def test_record_snapshot_writes_row(db: Database, price_cache: PriceCache) -> None:
    await service.record_snapshot(db, price_cache, DEFAULT_USER_ID)
    rows = await db.fetchall("SELECT total_value, recorded_at FROM portfolio_snapshots")
    assert len(rows) == 1
    assert rows[0]["total_value"] == 10_000.0


async def test_get_snapshots_returns_in_order(db: Database, price_cache: PriceCache) -> None:
    await service.record_snapshot(db, price_cache, DEFAULT_USER_ID)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 1.0)
    await service.record_snapshot(db, price_cache, DEFAULT_USER_ID)

    snaps = await service.get_snapshots(db, DEFAULT_USER_ID, limit=10)
    assert len(snaps) == 2
    assert snaps[0].recorded_at <= snaps[1].recorded_at


async def test_concurrent_buys_cannot_double_spend(
    db: Database, price_cache: PriceCache
) -> None:
    """Two concurrent buys that each fit the balance but together exceed it
    must not both succeed. Guards against the read-check-write race."""
    import asyncio

    # AAPL @ 190 * 30 = 5700. Two concurrent 30-share buys = 11,400 > 10,000.
    results = await asyncio.gather(
        service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 30.0),
        service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 30.0),
        return_exceptions=True,
    )
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, service.InsufficientFundsError)]
    assert len(successes) == 1
    assert len(failures) == 1

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.cash_balance >= 0
    assert state.cash_balance == pytest.approx(10_000.0 - 190.0 * 30.0)
    assert state.positions[0].quantity == 30.0


async def test_trade_is_atomic_on_insert_failure(
    db: Database, price_cache: PriceCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the trades INSERT fails, cash and positions must be rolled back."""
    import uuid as _uuid

    calls = {"n": 0}
    real_uuid4 = _uuid.uuid4

    def fake_uuid4():
        calls["n"] += 1
        # First uuid is for the positions INSERT; second is for the trades INSERT.
        if calls["n"] == 2:
            raise RuntimeError("simulated failure at trades insert")
        return real_uuid4()

    monkeypatch.setattr("app.portfolio.service.uuid.uuid4", fake_uuid4)

    with pytest.raises(RuntimeError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 1.0
        )

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.cash_balance == 10_000.0
    assert state.positions == []
    trades = await db.fetchall("SELECT id FROM trades")
    assert trades == []
