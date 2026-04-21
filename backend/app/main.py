"""FastAPI application factory and lifespan."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import get_settings
from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.health import router as health_router
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.watchlist.routes import router as watchlist_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Construct the FastAPI app with all routers and a lifespan wired in.

    The PriceCache is created here and captured by both the SSE router
    (which needs it at router-creation time) and the lifespan (which hands
    it to the MarketDataSource).
    """
    cache = PriceCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = get_settings()

        app.state.price_cache = cache

        db = Database(settings.db_path)
        await db.connect()
        await db.initialize()
        app.state.db = db

        source = create_market_data_source(cache)
        watchlist_rows = await db.fetchall(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (DEFAULT_USER_ID,)
        )
        tickers = [row["ticker"] for row in watchlist_rows]
        await source.start(tickers)
        app.state.market_source = source

        logger.info("FinAlly backend started with %d tickers", len(tickers))

        try:
            yield
        finally:
            await source.stop()
            await db.close()

    app = FastAPI(title="FinAlly", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(create_stream_router(cache))
    app.include_router(watchlist_router)
    return app
