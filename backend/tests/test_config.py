"""Tests for app.config.get_settings."""

from __future__ import annotations

from collections.abc import Generator

import pytest

from app import config


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Generator[None, None, None]:
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MOCK", raising=False)
    monkeypatch.delenv("FINALLY_DB_PATH", raising=False)

    settings = config.get_settings()

    assert settings.openrouter_api_key == ""
    assert settings.massive_api_key == ""
    assert settings.llm_mock is False
    assert settings.db_path.endswith("db/finally.db")


def test_llm_mock_truthy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ["true", "TRUE", "1", "yes", "YeS"]:
        config.get_settings.cache_clear()
        monkeypatch.setenv("LLM_MOCK", value)
        assert config.get_settings().llm_mock is True


def test_llm_mock_falsy_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for value in ["false", "0", "no", "", "anything-else"]:
        config.get_settings.cache_clear()
        monkeypatch.setenv("LLM_MOCK", value)
        assert config.get_settings().llm_mock is False


def test_custom_db_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINALLY_DB_PATH", "/tmp/custom.db")
    assert config.get_settings().db_path == "/tmp/custom.db"
