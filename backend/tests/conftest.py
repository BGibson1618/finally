"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.db.database import Database
from app.market import PriceCache


@pytest.fixture
def event_loop_policy():
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    """A fresh, seeded Database on a temp file. Closed after the test."""
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    await database.initialize()
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def price_cache() -> PriceCache:
    """A PriceCache preloaded with realistic prices for the default watchlist."""
    cache = PriceCache()
    seeds = {
        "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 185.0,
        "TSLA": 250.0, "NVDA": 800.0, "META": 500.0, "JPM": 195.0,
        "V": 280.0, "NFLX": 600.0,
    }
    for ticker, price in seeds.items():
        cache.update(ticker, price)
    return cache
