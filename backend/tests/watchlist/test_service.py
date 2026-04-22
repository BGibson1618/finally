"""Tests for watchlist service functions."""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID, DEFAULT_WATCHLIST
from app.market import PriceCache
from app.watchlist import service


async def test_list_watchlist_default(db: Database, price_cache: PriceCache) -> None:
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    tickers = sorted(e["ticker"] for e in entries)
    assert tickers == sorted(DEFAULT_WATCHLIST)
    # Every entry has a price from the cache
    for e in entries:
        assert e["price"] is not None


async def test_add_ticker_normalizes_case(db: Database, price_cache: PriceCache) -> None:
    entry = await service.add_ticker(db, "pypl", DEFAULT_USER_ID)
    assert entry["ticker"] == "PYPL"

    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    assert "PYPL" in {e["ticker"] for e in entries}


async def test_add_ticker_duplicate_is_no_op(db: Database, price_cache: PriceCache) -> None:
    await service.add_ticker(db, "AAPL", DEFAULT_USER_ID)  # already seeded
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    count = sum(1 for e in entries if e["ticker"] == "AAPL")
    assert count == 1


async def test_add_ticker_rejects_empty(db: Database) -> None:
    with pytest.raises(ValueError):
        await service.add_ticker(db, "", DEFAULT_USER_ID)


async def test_remove_ticker(db: Database, price_cache: PriceCache) -> None:
    await service.remove_ticker(db, "AAPL", DEFAULT_USER_ID)
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    assert "AAPL" not in {e["ticker"] for e in entries}


async def test_remove_ticker_not_present_raises_keyerror(db: Database) -> None:
    with pytest.raises(KeyError):
        await service.remove_ticker(db, "DOESNOTEXIST", DEFAULT_USER_ID)


async def test_list_entry_includes_missing_price_as_none(db: Database, price_cache: PriceCache) -> None:
    await service.add_ticker(db, "PYPL", DEFAULT_USER_ID)  # not in price_cache fixture
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    pypl = next(e for e in entries if e["ticker"] == "PYPL")
    assert pypl["price"] is None
