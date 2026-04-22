"""HTTP route for /api/chat."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.chat import service
from app.chat.models import ChatRequest, ChatResponse
from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.dependencies import get_db, get_market_source, get_price_cache
from app.market import MarketDataSource, PriceCache

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
    source: MarketDataSource = Depends(get_market_source),
) -> ChatResponse:
    return await service.handle_user_message(
        db,
        cache,
        source,
        DEFAULT_USER_ID,
        body.message,
        confirm_actions=body.confirm_actions,
    )
