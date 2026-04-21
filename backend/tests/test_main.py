"""Top-level app tests: health + lifespan."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("FINALLY_DB_PATH", str(tmp_path / "finally.db"))
    monkeypatch.setenv("LLM_MOCK", "true")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    from app import config
    config.get_settings.cache_clear()

    from app.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


def test_health(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_lifespan_creates_db_file(client: TestClient) -> None:
    db_path = os.environ["FINALLY_DB_PATH"]
    assert Path(db_path).exists()


def test_smoke_full_flow(client: TestClient) -> None:
    # Watchlist is seeded
    assert client.get("/api/watchlist").status_code == 200

    # Portfolio is the expected starting state
    state = client.get("/api/portfolio").json()
    assert state["cash_balance"] == 10_000.0

    # Chat-driven trade
    chat = client.post("/api/chat", json={"message": "buy 1 AAPL"}).json()
    assert any(
        a["kind"] == "trade" and a["status"] == "ok" for a in chat["executed_actions"]
    )

    # Portfolio reflects the trade
    state = client.get("/api/portfolio").json()
    assert state["cash_balance"] < 10_000.0
    assert any(p["ticker"] == "AAPL" for p in state["positions"])

    # History has at least one snapshot (recorded by the trade path)
    history = client.get("/api/portfolio/history").json()
    assert len(history) >= 1

    # SSE endpoint is reachable (status 200 + text/event-stream)
    with client.stream("GET", "/api/stream/prices") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
