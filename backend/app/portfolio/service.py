"""Portfolio valuation and trade execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import aiosqlite

from app.db.database import Database
from app.market import PriceCache
from app.portfolio.models import PortfolioState, Position, Snapshot, TradeResult


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _position_from_row(row: aiosqlite.Row, price_cache: PriceCache) -> Position:
    update = price_cache.get(row["ticker"])
    current_price = update.price if update else None
    market_value = (current_price * row["quantity"]) if current_price is not None else None
    cost_basis = row["quantity"] * row["avg_cost"]
    if market_value is not None:
        pl = market_value - cost_basis
        pl_pct = (pl / cost_basis * 100) if cost_basis else None
    else:
        pl = None
        pl_pct = None
    return Position(
        ticker=row["ticker"],
        quantity=row["quantity"],
        avg_cost=row["avg_cost"],
        current_price=current_price,
        market_value=market_value,
        unrealized_pl=pl,
        unrealized_pl_percent=pl_pct,
    )


async def get_cash_balance(db: Database, user_id: str) -> float:
    row = await db.fetchone(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    )
    return float(row["cash_balance"]) if row else 0.0


async def get_portfolio(
    db: Database, price_cache: PriceCache, user_id: str
) -> PortfolioState:
    cash = await get_cash_balance(db, user_id)
    rows = await db.fetchall(
        "SELECT ticker, quantity, avg_cost FROM positions "
        "WHERE user_id = ? AND quantity > 0 ORDER BY ticker",
        (user_id,),
    )
    positions = [_position_from_row(r, price_cache) for r in rows]
    positions_value = sum(p.market_value or 0.0 for p in positions)
    unrealized_pl = sum(p.unrealized_pl or 0.0 for p in positions)
    return PortfolioState(
        cash_balance=cash,
        total_value=cash + positions_value,
        positions_value=positions_value,
        unrealized_pl=unrealized_pl,
        positions=positions,
    )


class TradeError(Exception):
    """Base class for trade validation errors."""


class InsufficientFundsError(TradeError):
    pass


class InsufficientSharesError(TradeError):
    pass


class UnknownTickerError(TradeError):
    pass


async def execute_trade(
    db: Database,
    price_cache: PriceCache,
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
) -> TradeResult:
    """Execute a market buy or sell at the current cache price.

    Raises:
        ValueError: if quantity <= 0 or side is invalid
        UnknownTickerError: no price available for the ticker
        InsufficientFundsError: buy exceeds cash balance
        InsufficientSharesError: sell exceeds held quantity
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if side not in ("buy", "sell"):
        raise ValueError(f"invalid side: {side}")

    symbol = ticker.strip().upper()
    update = price_cache.get(symbol)
    if update is None:
        raise UnknownTickerError(f"no price for {symbol}")
    price = update.price

    cash = await get_cash_balance(db, user_id)
    position_row = await db.fetchone(
        "SELECT id, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, symbol),
    )

    if side == "buy":
        cost = price * quantity
        if cost > cash:
            raise InsufficientFundsError(f"needs {cost:.2f}, have {cash:.2f}")
        await _apply_buy(db, user_id, symbol, quantity, price, position_row)
    else:  # sell
        owned = position_row["quantity"] if position_row else 0.0
        if quantity > owned:
            raise InsufficientSharesError(f"owns {owned}, tried to sell {quantity}")
        await _apply_sell(db, user_id, symbol, quantity, price, position_row)

    now = _utc_iso()
    await db.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, symbol, side, quantity, price, now),
    )
    return TradeResult(
        ticker=symbol, side=side, quantity=quantity, price=price, executed_at=now
    )


async def _apply_buy(
    db: Database, user_id: str, ticker: str, qty: float, price: float, position_row
) -> None:
    now = _utc_iso()
    proceeds = price * qty
    await db.execute(
        "UPDATE users_profile SET cash_balance = cash_balance - ? WHERE id = ?",
        (proceeds, user_id),
    )
    if position_row is None:
        await db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, ticker, qty, price, now),
        )
    else:
        new_qty = position_row["quantity"] + qty
        new_avg = (
            position_row["quantity"] * position_row["avg_cost"] + qty * price
        ) / new_qty
        await db.execute(
            "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE id = ?",
            (new_qty, new_avg, now, position_row["id"]),
        )


async def _apply_sell(
    db: Database, user_id: str, ticker: str, qty: float, price: float, position_row
) -> None:
    now = _utc_iso()
    proceeds = price * qty
    await db.execute(
        "UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?",
        (proceeds, user_id),
    )
    new_qty = position_row["quantity"] - qty
    if new_qty <= 1e-9:
        await db.execute("DELETE FROM positions WHERE id = ?", (position_row["id"],))
    else:
        await db.execute(
            "UPDATE positions SET quantity = ?, updated_at = ? WHERE id = ?",
            (new_qty, now, position_row["id"]),
        )


async def record_snapshot(
    db: Database, price_cache: PriceCache, user_id: str
) -> Snapshot:
    """Record the current total portfolio value."""
    state = await get_portfolio(db, price_cache, user_id)
    now = _utc_iso()
    await db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, state.total_value, now),
    )
    return Snapshot(total_value=state.total_value, recorded_at=now)


async def get_snapshots(db: Database, user_id: str, limit: int = 500) -> list[Snapshot]:
    rows = await db.fetchall(
        "SELECT total_value, recorded_at FROM portfolio_snapshots "
        "WHERE user_id = ? ORDER BY recorded_at ASC LIMIT ?",
        (user_id, limit),
    )
    return [Snapshot(total_value=r["total_value"], recorded_at=r["recorded_at"]) for r in rows]
