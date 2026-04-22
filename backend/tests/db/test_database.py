"""Tests for app.db.database.Database."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_CASH, DEFAULT_USER_ID, DEFAULT_WATCHLIST


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    await database.initialize()
    yield database
    await database.close()


async def test_initialize_creates_all_tables(db: Database) -> None:
    rows = await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    }.issubset(names)


async def test_initialize_seeds_default_user(db: Database) -> None:
    row = await db.fetchone(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    )
    assert row is not None
    assert row["cash_balance"] == DEFAULT_CASH


async def test_initialize_seeds_default_watchlist(db: Database) -> None:
    rows = await db.fetchall(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker",
        (DEFAULT_USER_ID,),
    )
    tickers = [row["ticker"] for row in rows]
    assert sorted(tickers) == sorted(DEFAULT_WATCHLIST)


async def test_initialize_is_idempotent(tmp_path: Path) -> None:
    path = str(tmp_path / "idem.db")
    db1 = Database(path)
    await db1.connect()
    await db1.initialize()
    await db1.close()

    db2 = Database(path)
    await db2.connect()
    await db2.initialize()
    rows = await db2.fetchall(
        "SELECT ticker FROM watchlist WHERE user_id = ?", ("default",)
    )
    await db2.close()

    # Should still have exactly the seed list (no duplicates)
    assert len(rows) == len(DEFAULT_WATCHLIST)


async def test_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "path" / "finally.db"
    database = Database(str(nested))
    await database.connect()
    await database.initialize()
    await database.close()
    assert nested.exists()


async def test_row_factory_returns_mappings(db: Database) -> None:
    row = await db.fetchone("SELECT cash_balance FROM users_profile WHERE id = 'default'")
    assert row is not None
    # aiosqlite.Row supports index AND key access
    assert row["cash_balance"] == DEFAULT_CASH


async def test_transaction_commits_on_success(db: Database) -> None:
    async with db.transaction() as conn:
        await conn.execute(
            "UPDATE users_profile SET cash_balance = 42 WHERE id = ?",
            (DEFAULT_USER_ID,),
        )
    row = await db.fetchone(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    )
    assert row["cash_balance"] == 42


async def test_transaction_rolls_back_on_exception(db: Database) -> None:
    with pytest.raises(RuntimeError):
        async with db.transaction() as conn:
            await conn.execute(
                "UPDATE users_profile SET cash_balance = 42 WHERE id = ?",
                (DEFAULT_USER_ID,),
            )
            raise RuntimeError("boom")
    row = await db.fetchone(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    )
    assert row["cash_balance"] == DEFAULT_CASH


async def test_transaction_serializes_concurrent_callers(db: Database) -> None:
    """Two concurrent transactions must not interleave on the shared connection."""
    import asyncio

    async def increment_by(n: float) -> None:
        async with db.transaction() as conn:
            cursor = await conn.execute(
                "SELECT cash_balance FROM users_profile WHERE id = ?",
                (DEFAULT_USER_ID,),
            )
            row = await cursor.fetchone()
            # Yield to the event loop to maximize interleaving opportunity.
            await asyncio.sleep(0)
            await conn.execute(
                "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
                (row["cash_balance"] + n, DEFAULT_USER_ID),
            )

    await asyncio.gather(increment_by(1.0), increment_by(2.0), increment_by(3.0))
    row = await db.fetchone(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    )
    assert row["cash_balance"] == DEFAULT_CASH + 6.0
