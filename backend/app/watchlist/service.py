"""Watchlist CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import Database
from app.market import PriceCache


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(ticker: str) -> str:
    t = ticker.strip().upper()
    if not t:
        raise ValueError("ticker must be non-empty")
    return t


async def list_watchlist(
    db: Database, price_cache: PriceCache, user_id: str
) -> list[dict[str, Any]]:
    """Return watchlist entries, each joined with the latest cached price (or None)."""
    rows = await db.fetchall(
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
        (user_id,),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        update = price_cache.get(row["ticker"])
        result.append(
            {
                "ticker": row["ticker"],
                "added_at": row["added_at"],
                "price": update.price if update else None,
                "previous_price": update.previous_price if update else None,
                "change": update.change if update else None,
                "change_percent": update.change_percent if update else None,
                "direction": update.direction if update else None,
            }
        )
    return result


async def add_ticker(db: Database, ticker: str, user_id: str) -> dict[str, Any]:
    """Insert a ticker into the watchlist. Duplicate is a no-op."""
    symbol = _normalize(ticker)
    existing = await db.fetchone(
        "SELECT added_at FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, symbol),
    )
    if existing is not None:
        return {"ticker": symbol, "added_at": existing["added_at"]}

    added_at = _utc_iso()
    await db.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, symbol, added_at),
    )
    return {"ticker": symbol, "added_at": added_at}


async def remove_ticker(db: Database, ticker: str, user_id: str) -> None:
    """Delete a ticker from the watchlist. Raises KeyError if not present."""
    symbol = _normalize(ticker)
    row = await db.fetchone(
        "SELECT id FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, symbol),
    )
    if row is None:
        raise KeyError(symbol)
    await db.execute("DELETE FROM watchlist WHERE id = ?", (row["id"],))
