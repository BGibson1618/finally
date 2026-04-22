"""HTTP routes for /api/watchlist."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.dependencies import get_db, get_market_source, get_price_cache
from app.market import MarketDataSource, PriceCache
from app.portfolio.models import TICKER_PATTERN
from app.watchlist import service

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class TickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=6, pattern=TICKER_PATTERN)


@router.get("")
async def get_watchlist(
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
) -> list[dict]:
    return await service.list_watchlist(db, cache, DEFAULT_USER_ID)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_watchlist(
    body: TickerRequest,
    db: Database = Depends(get_db),
    source: MarketDataSource = Depends(get_market_source),
) -> dict:
    try:
        entry = await service.add_ticker(db, body.ticker, DEFAULT_USER_ID)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await source.add_ticker(entry["ticker"])
    return entry


@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    ticker: str,
    db: Database = Depends(get_db),
    source: MarketDataSource = Depends(get_market_source),
) -> None:
    symbol = ticker.strip().upper()
    try:
        await service.remove_ticker(db, symbol, DEFAULT_USER_ID)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Ticker {symbol} not in watchlist")
    await source.remove_ticker(symbol)
