"""HTTP tests for /api/portfolio."""

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


def test_get_portfolio_initial(client: TestClient) -> None:
    r = client.get("/api/portfolio")
    assert r.status_code == 200
    body = r.json()
    assert body["cash_balance"] == 10_000.0
    assert body["positions"] == []


def test_buy_trade(client: TestClient) -> None:
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1.0},
    )
    assert r.status_code == 201
    assert r.json()["ticker"] == "AAPL"

    portfolio = client.get("/api/portfolio").json()
    assert portfolio["cash_balance"] < 10_000.0
    assert len(portfolio["positions"]) == 1


def test_sell_more_than_owned_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "sell", "quantity": 5.0},
    )
    assert r.status_code == 400


def test_buy_unknown_ticker_returns_400(client: TestClient) -> None:
    r = client.post(
        "/api/portfolio/trade",
        json={"ticker": "DOESNOTEXIST", "side": "buy", "quantity": 1.0},
    )
    assert r.status_code == 400


def test_history_starts_empty(client: TestClient) -> None:
    r = client.get("/api/portfolio/history")
    assert r.status_code == 200
    assert r.json() == []


def test_history_populated_after_trade(client: TestClient) -> None:
    client.post(
        "/api/portfolio/trade",
        json={"ticker": "AAPL", "side": "buy", "quantity": 1.0},
    )
    r = client.get("/api/portfolio/history")
    assert r.status_code == 200
    snaps = r.json()
    assert len(snaps) >= 1
    assert snaps[-1]["total_value"] > 0
