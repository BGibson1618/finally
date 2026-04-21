"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the project root (one level above backend/) once at import time.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env", override=False)

_TRUTHY = {"true", "1", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime settings."""

    openrouter_api_key: str
    massive_api_key: str
    llm_mock: bool
    db_path: str


def _default_db_path() -> str:
    return str(_PROJECT_ROOT / "db" / "finally.db")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings. Cached; call get_settings.cache_clear() in tests."""
    return Settings(
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        massive_api_key=os.environ.get("MASSIVE_API_KEY", ""),
        llm_mock=os.environ.get("LLM_MOCK", "").strip().lower() in _TRUTHY,
        db_path=os.environ.get("FINALLY_DB_PATH") or _default_db_path(),
    )
