"""Tests for the SSE stream router factory."""

from __future__ import annotations

from app.market import PriceCache, create_stream_router


def test_factory_returns_independent_routers() -> None:
    """Each call must produce a fresh router — no shared module-level state."""
    r1 = create_stream_router(PriceCache())
    r2 = create_stream_router(PriceCache())

    assert r1 is not r2
    assert len(r1.routes) == 1
    assert len(r2.routes) == 1


def test_router_registers_prices_route() -> None:
    router = create_stream_router(PriceCache())
    paths = {getattr(r, "path", None) for r in router.routes}
    assert "/api/stream/prices" in paths
