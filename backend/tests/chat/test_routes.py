"""HTTP tests for /api/chat."""

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


def test_chat_echoes_mock_reply(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": "hello there"})
    assert r.status_code == 200
    body = r.json()
    assert "message" in body
    assert body["executed_actions"] == []
    assert body["proposed_actions"] == []


def test_chat_proposes_buy_without_executing(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": "buy 1 AAPL"})
    assert r.status_code == 200
    body = r.json()
    assert body["executed_actions"] == []
    assert len(body["proposed_actions"]) == 1
    assert body["proposed_actions"][0]["kind"] == "trade"
    assert body["proposed_actions"][0]["ticker"] == "AAPL"


def test_chat_confirmation_executes_proposed(client: TestClient) -> None:
    r1 = client.post("/api/chat", json={"message": "buy 1 AAPL"}).json()
    r2 = client.post(
        "/api/chat",
        json={"message": "confirm", "confirm_actions": r1["proposed_actions"]},
    ).json()
    actions = r2["executed_actions"]
    assert any(a["kind"] == "trade" and a["status"] == "ok" for a in actions)


def test_chat_rejects_empty_message(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422


def test_chat_rejects_invalid_ticker_in_confirm_actions(client: TestClient) -> None:
    r = client.post(
        "/api/chat",
        json={
            "message": "confirm",
            "confirm_actions": [
                {"kind": "trade", "ticker": "AAPL123", "side": "buy", "quantity": 1}
            ],
        },
    )
    assert r.status_code == 422
