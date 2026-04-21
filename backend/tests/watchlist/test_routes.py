"""HTTP tests for /api/watchlist."""

from __future__ import annotations

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
    with TestClient(create_app()) as c:
        yield c


def test_get_watchlist_returns_defaults(client: TestClient) -> None:
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    body = r.json()
    tickers = {e["ticker"] for e in body}
    assert {"AAPL", "GOOGL", "MSFT"}.issubset(tickers)
    assert all("price" in e for e in body)


def test_add_watchlist_entry(client: TestClient) -> None:
    r = client.post("/api/watchlist", json={"ticker": "pypl"})
    assert r.status_code == 201
    assert r.json()["ticker"] == "PYPL"
    # Confirm it shows up
    tickers = {e["ticker"] for e in client.get("/api/watchlist").json()}
    assert "PYPL" in tickers


def test_add_watchlist_empty_ticker_returns_400(client: TestClient) -> None:
    r = client.post("/api/watchlist", json={"ticker": ""})
    assert r.status_code == 400


def test_delete_watchlist_entry(client: TestClient) -> None:
    r = client.delete("/api/watchlist/AAPL")
    assert r.status_code == 204
    tickers = {e["ticker"] for e in client.get("/api/watchlist").json()}
    assert "AAPL" not in tickers


def test_delete_missing_returns_404(client: TestClient) -> None:
    r = client.delete("/api/watchlist/DOESNOTEXIST")
    assert r.status_code == 404
