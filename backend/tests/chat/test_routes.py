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


def test_chat_executes_buy(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": "buy 1 AAPL"})
    assert r.status_code == 200
    actions = r.json()["executed_actions"]
    assert any(a["kind"] == "trade" and a["status"] == "ok" for a in actions)


def test_chat_rejects_empty_message(client: TestClient) -> None:
    r = client.post("/api/chat", json={"message": ""})
    assert r.status_code == 422
