"""HTTP routes for /api/portfolio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.dependencies import get_db, get_price_cache
from app.market import PriceCache
from app.portfolio import service
from app.portfolio.models import PortfolioState, Snapshot, TradeRequest, TradeResult

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioState)
async def get_portfolio(
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
) -> PortfolioState:
    return await service.get_portfolio(db, cache, DEFAULT_USER_ID)


@router.post("/trade", response_model=TradeResult, status_code=status.HTTP_201_CREATED)
async def place_trade(
    body: TradeRequest,
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
) -> TradeResult:
    try:
        result = await service.execute_trade(
            db, cache, DEFAULT_USER_ID,
            ticker=body.ticker, side=body.side, quantity=body.quantity,
        )
    except (service.TradeError, ValueError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    # Record a snapshot immediately after trade (per PLAN.md §7)
    await service.record_snapshot(db, cache, DEFAULT_USER_ID)
    return result


@router.get("/history", response_model=list[Snapshot])
async def get_history(
    db: Database = Depends(get_db),
) -> list[Snapshot]:
    return await service.get_snapshots(db, DEFAULT_USER_ID)
