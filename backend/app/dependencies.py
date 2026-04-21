"""Shared FastAPI dependency providers.

Each function reads its target from request.app.state. This keeps services
testable (construct the app with overridden state) and avoids module globals.
"""

from __future__ import annotations

from fastapi import Request

from app.db.database import Database
from app.market import MarketDataSource, PriceCache


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_price_cache(request: Request) -> PriceCache:
    return request.app.state.price_cache


def get_market_source(request: Request) -> MarketDataSource:
    return request.app.state.market_source
