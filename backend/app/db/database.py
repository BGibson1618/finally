"""Async SQLite wrapper with lazy schema initialization and seeding."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite

from .seed_data import DEFAULT_CASH, DEFAULT_USER_ID, DEFAULT_WATCHLIST


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin async wrapper around a single aiosqlite connection.

    One connection per application (SQLite single-writer model). Use the
    helpers (execute/fetchall/fetchone) for all queries so a shared connection
    and Row factory are enforced.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None
        # Serializes transactions on the single shared connection: BEGIN/COMMIT
        # spans multiple awaits and SQLite can't nest transactions on one conn.
        self._tx_lock = asyncio.Lock()

    @property
    def path(self) -> str:
        return self._path

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first")
        return self._conn

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def initialize(self) -> None:
        """Create tables (idempotent) and seed defaults if empty."""
        schema_sql = resources.files("app.db").joinpath("schema.sql").read_text()
        await self.connection.executescript(schema_sql)
        await self.connection.commit()
        await self._seed_defaults()

    async def _seed_defaults(self) -> None:
        row = await self.fetchone(
            "SELECT id FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
        )
        if row is None:
            await self.execute(
                "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                (DEFAULT_USER_ID, DEFAULT_CASH, _utc_iso()),
            )

        existing = await self.fetchall(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (DEFAULT_USER_ID,)
        )
        existing_tickers = {r["ticker"] for r in existing}
        for ticker in DEFAULT_WATCHLIST:
            if ticker not in existing_tickers:
                await self.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, _utc_iso()),
                )

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self.connection.execute(sql, params)
        await self.connection.commit()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Run a block of statements as a single atomic transaction.

        Serialized by an asyncio.Lock: only one transaction at a time on the
        shared connection. Commits on clean exit, rolls back on exception.
        """
        async with self._tx_lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                await self.connection.rollback()
                raise
            else:
                await self.connection.commit()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self.connection.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with self.connection.execute(sql, params) as cursor:
            return await cursor.fetchone()
