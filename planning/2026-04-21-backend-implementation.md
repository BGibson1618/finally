# Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the FinAlly backend by building the database layer, FastAPI application, portfolio/watchlist/chat endpoints, background tasks, and LLM integration — producing a fully functional API surface that the frontend can integrate against.

**Architecture:** A FastAPI application wired via an async `lifespan` that initializes a lazy-seeded SQLite database (via `aiosqlite`) and a shared `PriceCache` fed by the existing `MarketDataSource`. Routers expose REST endpoints under `/api/*` and the pre-built SSE streamer under `/api/stream/*`. A chat router calls an LLM (LiteLLM → OpenRouter → Cerebras with structured outputs) and auto-executes trades/watchlist changes through the same services used by the REST endpoints. A background task periodically records portfolio value snapshots for the P&L chart.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, uv, aiosqlite, python-dotenv, litellm, pydantic, pytest, pytest-asyncio.

---

## Starting State (verify before you begin)

- Working dir: `/home/bgibs/projects/finally/backend`
- `app/market/` is complete (models, cache, interface, simulator, massive_client, factory, stream, seed_prices) — do NOT modify these files
- `app/__init__.py` exists with docstring only: `"""FinAlly backend application."""`
- `tests/conftest.py` exists with a single `event_loop_policy` fixture
- `pyproject.toml` has FastAPI, uvicorn, numpy, massive, rich; `dev` extras have pytest, pytest-asyncio, pytest-cov, ruff
- `backend/db/` and `backend/frontend/` do **not** exist
- Database file `/home/bgibs/projects/finally/db/finally.db` does **not** exist yet
- Run `uv sync --extra dev` once before starting to ensure the venv is built

**Setup verification command** (run once at start):

```bash
cd /home/bgibs/projects/finally/backend
uv sync --extra dev
uv run --extra dev pytest -q
```

Expected: all existing 73 market tests pass.

---

## File Structure (to be created)

```
backend/
├── app/
│   ├── __init__.py                  # (exists, unchanged)
│   ├── config.py                    # NEW — settings loaded from env
│   ├── main.py                      # NEW — FastAPI app + lifespan
│   ├── dependencies.py              # NEW — FastAPI dependency providers
│   ├── db/
│   │   ├── __init__.py              # NEW
│   │   ├── schema.sql               # NEW — DDL for 6 tables
│   │   ├── database.py              # NEW — connection + init + seed
│   │   └── seed_data.py             # NEW — default user + watchlist rows
│   ├── watchlist/
│   │   ├── __init__.py              # NEW
│   │   ├── service.py               # NEW — CRUD ops
│   │   └── routes.py                # NEW — /api/watchlist router
│   ├── portfolio/
│   │   ├── __init__.py              # NEW
│   │   ├── models.py                # NEW — Pydantic response models
│   │   ├── service.py               # NEW — valuation + trade execution
│   │   ├── snapshots.py             # NEW — 30s background task
│   │   └── routes.py                # NEW — /api/portfolio router
│   ├── chat/
│   │   ├── __init__.py              # NEW
│   │   ├── models.py                # NEW — ChatResponse Pydantic schema
│   │   ├── llm.py                   # NEW — real + mock LLM callers
│   │   ├── service.py               # NEW — orchestration
│   │   └── routes.py                # NEW — /api/chat router
│   ├── health.py                    # NEW — /api/health router
│   └── market/                      # (exists, unchanged)
├── tests/
│   ├── conftest.py                  # MODIFY — add shared fixtures
│   ├── market/                      # (exists, unchanged)
│   ├── db/
│   │   ├── __init__.py              # NEW
│   │   └── test_database.py         # NEW
│   ├── watchlist/
│   │   ├── __init__.py              # NEW
│   │   ├── test_service.py          # NEW
│   │   └── test_routes.py           # NEW
│   ├── portfolio/
│   │   ├── __init__.py              # NEW
│   │   ├── test_service.py          # NEW
│   │   ├── test_snapshots.py        # NEW
│   │   └── test_routes.py           # NEW
│   ├── chat/
│   │   ├── __init__.py              # NEW
│   │   ├── test_llm_mock.py         # NEW
│   │   ├── test_service.py          # NEW
│   │   └── test_routes.py           # NEW
│   └── test_main.py                 # NEW — app-level smoke + health
├── pyproject.toml                    # MODIFY — add deps
└── uv.lock                           # auto-regenerates on uv add
```

At project root:
- `.env.example` (NEW, project root: `/home/bgibs/projects/finally/.env.example`)
- `.env` is gitignored (user creates locally if desired)

---

## Ground Rules for the Implementing Agent

1. **TDD:** For every production code change, write the test first, confirm it fails, write the minimum implementation, confirm it passes, commit.
2. **Run all tests after each task** using `uv run --extra dev pytest -q` — never let the suite go red.
3. **Lint after each task**: `uv run --extra dev ruff check app/ tests/` — fix issues before committing.
4. **Commit messages** use the existing conventional style already in the repo (`feat:`, `fix:`, `test:`, `chore:`). Example recent commit: `"feat: add Rich terminal demo for market data simulator"`.
5. **Never modify `app/market/`** — it is complete and has its own test suite.
6. **Python style:** use `from __future__ import annotations`, type hints on all public functions, no defensive programming, short docstrings. Match the style of `app/market/*.py`.
7. **Database access:** every query goes through an `aiosqlite.Connection` passed in; never open ad-hoc connections inside services or routes.
8. **No global singletons** — use FastAPI dependency injection (`app.state` + `Depends(...)`) as established by the market `create_stream_router` pattern.
9. **If a step says to run a command, actually run it** and paste the relevant output into your thought process to verify.

---

## Task 1: Project dependencies & environment config

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/config.py`
- Create: `backend/tests/test_config.py`
- Create: `/home/bgibs/projects/finally/.env.example`

- [ ] **Step 1: Add runtime dependencies with uv**

```bash
cd /home/bgibs/projects/finally/backend
uv add aiosqlite python-dotenv litellm
```

Expected: `pyproject.toml` updated, `uv.lock` regenerated, output ends with `"Resolved N packages"` and no error.

- [ ] **Step 2: Add dev-only dependency for HTTP assertions**

```bash
uv add --optional dev httpx
```

(`httpx` is already a transitive dep of FastAPI's TestClient, but we pin it explicitly for the dev extra.)

- [ ] **Step 3: Create `.env.example` at the project root**

Write this to `/home/bgibs/projects/finally/.env.example` exactly:

```
# Required: OpenRouter API key for LLM chat functionality
OPENROUTER_API_KEY=your-openrouter-api-key-here

# Optional: Massive (Polygon.io) API key for real market data
# If not set, the built-in market simulator is used.
MASSIVE_API_KEY=

# Optional: Set to "true" for deterministic mock LLM responses (testing/CI)
LLM_MOCK=false

# Optional override for the SQLite database path. Defaults to db/finally.db.
FINALLY_DB_PATH=
```

- [ ] **Step 4: Write failing tests for config**

Create `backend/tests/test_config.py`:

```python
"""Tests for app.config.get_settings."""

from __future__ import annotations

import importlib

import pytest

from app import config


@pytest.fixture(autouse=True)
def _reset_settings_cache():
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
```

- [ ] **Step 5: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.config'` (or `ImportError`).

- [ ] **Step 6: Implement `app/config.py`**

```python
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
```

- [ ] **Step 7: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 8: Lint**

```bash
uv run --extra dev ruff check app/ tests/
```

Expected: no errors.

- [ ] **Step 9: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/app/config.py backend/tests/test_config.py .env.example
git commit -m "feat: add app config loader and .env.example"
```

---

## Task 2: Database schema and lazy initialization

**Files:**
- Create: `backend/app/db/__init__.py`
- Create: `backend/app/db/schema.sql`
- Create: `backend/app/db/seed_data.py`
- Create: `backend/app/db/database.py`
- Create: `backend/tests/db/__init__.py`
- Create: `backend/tests/db/test_database.py`

- [ ] **Step 1: Create `backend/app/db/__init__.py`**

```python
"""Database subsystem: schema, connection, lazy init, and seeding."""

from .database import Database, get_db

__all__ = ["Database", "get_db"]
```

- [ ] **Step 2: Create `backend/app/db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS users_profile (
    id           TEXT PRIMARY KEY,
    cash_balance REAL NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    id       TEXT PRIMARY KEY,
    user_id  TEXT NOT NULL DEFAULT 'default',
    ticker   TEXT NOT NULL,
    added_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS positions (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default',
    ticker     TEXT NOT NULL,
    quantity   REAL NOT NULL,
    avg_cost   REAL NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, ticker)
);

CREATE TABLE IF NOT EXISTS trades (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    ticker      TEXT NOT NULL,
    side        TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    REAL NOT NULL,
    price       REAL NOT NULL,
    executed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trades_user_executed
    ON trades (user_id, executed_at DESC);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL DEFAULT 'default',
    total_value REAL NOT NULL,
    recorded_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshots_user_recorded
    ON portfolio_snapshots (user_id, recorded_at ASC);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL DEFAULT 'default',
    role       TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content    TEXT NOT NULL,
    actions    TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_user_created
    ON chat_messages (user_id, created_at ASC);
```

- [ ] **Step 3: Create `backend/app/db/seed_data.py`**

```python
"""Default data seeded on first database creation."""

from __future__ import annotations

DEFAULT_USER_ID = "default"
DEFAULT_CASH = 10_000.0

DEFAULT_WATCHLIST: list[str] = [
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
]
```

- [ ] **Step 4: Write failing tests for Database**

Create `backend/tests/db/__init__.py` (empty).

Create `backend/tests/db/test_database.py`:

```python
"""Tests for app.db.database.Database."""

from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_CASH, DEFAULT_USER_ID, DEFAULT_WATCHLIST


@pytest.fixture
async def db(tmp_path: Path) -> Database:
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    await database.initialize()
    yield database
    await database.close()


async def test_initialize_creates_all_tables(db: Database) -> None:
    rows = await db.fetchall(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert {
        "users_profile",
        "watchlist",
        "positions",
        "trades",
        "portfolio_snapshots",
        "chat_messages",
    }.issubset(names)


async def test_initialize_seeds_default_user(db: Database) -> None:
    row = await db.fetchone(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
    )
    assert row is not None
    assert row["cash_balance"] == DEFAULT_CASH


async def test_initialize_seeds_default_watchlist(db: Database) -> None:
    rows = await db.fetchall(
        "SELECT ticker FROM watchlist WHERE user_id = ? ORDER BY ticker",
        (DEFAULT_USER_ID,),
    )
    tickers = [row["ticker"] for row in rows]
    assert sorted(tickers) == sorted(DEFAULT_WATCHLIST)


async def test_initialize_is_idempotent(tmp_path: Path) -> None:
    path = str(tmp_path / "idem.db")
    db1 = Database(path)
    await db1.connect()
    await db1.initialize()
    await db1.close()

    db2 = Database(path)
    await db2.connect()
    await db2.initialize()
    rows = await db2.fetchall(
        "SELECT ticker FROM watchlist WHERE user_id = ?", ("default",)
    )
    await db2.close()

    # Should still have exactly the seed list (no duplicates)
    assert len(rows) == len(DEFAULT_WATCHLIST)


async def test_creates_parent_directory(tmp_path: Path) -> None:
    nested = tmp_path / "nested" / "path" / "finally.db"
    database = Database(str(nested))
    await database.connect()
    await database.initialize()
    await database.close()
    assert nested.exists()


async def test_row_factory_returns_mappings(db: Database) -> None:
    row = await db.fetchone("SELECT cash_balance FROM users_profile WHERE id = 'default'")
    assert row is not None
    # aiosqlite.Row supports index AND key access
    assert row["cash_balance"] == DEFAULT_CASH
```

- [ ] **Step 5: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/db/ -v
```

Expected: `ModuleNotFoundError: No module named 'app.db.database'`.

- [ ] **Step 6: Implement `backend/app/db/database.py`**

```python
"""Async SQLite wrapper with lazy schema initialization and seeding."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import Request

from .seed_data import DEFAULT_CASH, DEFAULT_USER_ID, DEFAULT_WATCHLIST


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """Thin async wrapper around a single aiosqlite connection.

    One connection per application (SQLite single-writer model). Use the
    helpers (execute/fetchall/fetchone) for all queries so a shared connection
    and Row factory are enforced.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def path(self) -> str:
        return self._path

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database.connect() must be called first")
        return self._conn

    async def connect(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def initialize(self) -> None:
        """Create tables (idempotent) and seed defaults if empty."""
        schema_sql = resources.files("app.db").joinpath("schema.sql").read_text()
        await self.connection.executescript(schema_sql)
        await self.connection.commit()
        await self._seed_defaults()

    async def _seed_defaults(self) -> None:
        row = await self.fetchone(
            "SELECT id FROM users_profile WHERE id = ?", (DEFAULT_USER_ID,)
        )
        if row is None:
            await self.execute(
                "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
                (DEFAULT_USER_ID, DEFAULT_CASH, _utc_iso()),
            )

        existing = await self.fetchall(
            "SELECT ticker FROM watchlist WHERE user_id = ?", (DEFAULT_USER_ID,)
        )
        existing_tickers = {r["ticker"] for r in existing}
        for ticker in DEFAULT_WATCHLIST:
            if ticker not in existing_tickers:
                await self.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, _utc_iso()),
                )

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        await self.connection.execute(sql, params)
        await self.connection.commit()

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self.connection.execute(sql, params) as cursor:
            return list(await cursor.fetchall())

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        async with self.connection.execute(sql, params) as cursor:
            return await cursor.fetchone()


def get_db(request: Request) -> Database:
    """FastAPI dependency: returns the Database stored on app.state."""
    return request.app.state.db
```

- [ ] **Step 7: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/db/ -v
```

Expected: 6 passed.

- [ ] **Step 8: Lint**

```bash
uv run --extra dev ruff check app/ tests/
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/db backend/tests/db
git commit -m "feat: add SQLite schema, lazy init, and default seed data"
```

---

## Task 3: Shared test fixtures

**Files:**
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Replace `backend/tests/conftest.py` with:**

```python
"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import pytest

from app.db.database import Database
from app.market import PriceCache


@pytest.fixture
def event_loop_policy():
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    """A fresh, seeded Database on a temp file. Closed after the test."""
    database = Database(str(tmp_path / "test.db"))
    await database.connect()
    await database.initialize()
    try:
        yield database
    finally:
        await database.close()


@pytest.fixture
def price_cache() -> PriceCache:
    """A PriceCache preloaded with realistic prices for the default watchlist."""
    cache = PriceCache()
    seeds = {
        "AAPL": 190.0, "GOOGL": 175.0, "MSFT": 420.0, "AMZN": 185.0,
        "TSLA": 250.0, "NVDA": 800.0, "META": 500.0, "JPM": 195.0,
        "V": 280.0, "NFLX": 600.0,
    }
    for ticker, price in seeds.items():
        cache.update(ticker, price)
    return cache
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
uv run --extra dev pytest -q
```

Expected: all market tests + config tests + db tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: add shared db and price_cache fixtures"
```

---

## Task 4: Health endpoint & FastAPI app skeleton

**Files:**
- Create: `backend/app/health.py`
- Create: `backend/app/dependencies.py`
- Create: `backend/app/main.py`
- Create: `backend/tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/test_main.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 3: Implement `backend/app/health.py`**

```python
"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Implement `backend/app/dependencies.py`**

```python
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
```

- [ ] **Step 5: Implement `backend/app/main.py`**

```python
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
    return app
```

- [ ] **Step 6: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/test_main.py -v
```

Expected: 2 passed.

- [ ] **Step 7: Full suite + lint**

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check app/ tests/
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/health.py backend/app/dependencies.py backend/app/main.py backend/tests/test_main.py
git commit -m "feat: add FastAPI app factory, lifespan, and /api/health"
```

---

## Task 5: Watchlist service

**Files:**
- Create: `backend/app/watchlist/__init__.py`
- Create: `backend/app/watchlist/service.py`
- Create: `backend/tests/watchlist/__init__.py`
- Create: `backend/tests/watchlist/test_service.py`

- [ ] **Step 1: Create `backend/app/watchlist/__init__.py`**

```python
"""Watchlist subsystem."""
```

- [ ] **Step 2: Write failing tests**

Create `backend/tests/watchlist/__init__.py` (empty).

Create `backend/tests/watchlist/test_service.py`:

```python
"""Tests for watchlist service functions."""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID, DEFAULT_WATCHLIST
from app.market import PriceCache
from app.watchlist import service


async def test_list_watchlist_default(db: Database, price_cache: PriceCache) -> None:
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    tickers = sorted(e["ticker"] for e in entries)
    assert tickers == sorted(DEFAULT_WATCHLIST)
    # Every entry has a price from the cache
    for e in entries:
        assert e["price"] is not None


async def test_add_ticker_normalizes_case(db: Database, price_cache: PriceCache) -> None:
    entry = await service.add_ticker(db, "pypl", DEFAULT_USER_ID)
    assert entry["ticker"] == "PYPL"

    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    assert "PYPL" in {e["ticker"] for e in entries}


async def test_add_ticker_duplicate_is_no_op(db: Database, price_cache: PriceCache) -> None:
    await service.add_ticker(db, "AAPL", DEFAULT_USER_ID)  # already seeded
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    count = sum(1 for e in entries if e["ticker"] == "AAPL")
    assert count == 1


async def test_add_ticker_rejects_empty(db: Database) -> None:
    with pytest.raises(ValueError):
        await service.add_ticker(db, "", DEFAULT_USER_ID)


async def test_remove_ticker(db: Database, price_cache: PriceCache) -> None:
    await service.remove_ticker(db, "AAPL", DEFAULT_USER_ID)
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    assert "AAPL" not in {e["ticker"] for e in entries}


async def test_remove_ticker_not_present_raises_keyerror(db: Database) -> None:
    with pytest.raises(KeyError):
        await service.remove_ticker(db, "DOESNOTEXIST", DEFAULT_USER_ID)


async def test_list_entry_includes_missing_price_as_none(db: Database, price_cache: PriceCache) -> None:
    await service.add_ticker(db, "PYPL", DEFAULT_USER_ID)  # not in price_cache fixture
    entries = await service.list_watchlist(db, price_cache, DEFAULT_USER_ID)
    pypl = next(e for e in entries if e["ticker"] == "PYPL")
    assert pypl["price"] is None
```

- [ ] **Step 3: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/watchlist/ -v
```

Expected: `ModuleNotFoundError: No module named 'app.watchlist.service'`.

- [ ] **Step 4: Implement `backend/app/watchlist/service.py`**

```python
"""Watchlist CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.database import Database
from app.market import PriceCache


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize(ticker: str) -> str:
    t = ticker.strip().upper()
    if not t:
        raise ValueError("ticker must be non-empty")
    return t


async def list_watchlist(
    db: Database, price_cache: PriceCache, user_id: str
) -> list[dict[str, Any]]:
    """Return watchlist entries, each joined with the latest cached price (or None)."""
    rows = await db.fetchall(
        "SELECT ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at",
        (user_id,),
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        update = price_cache.get(row["ticker"])
        result.append(
            {
                "ticker": row["ticker"],
                "added_at": row["added_at"],
                "price": update.price if update else None,
                "previous_price": update.previous_price if update else None,
                "change": update.change if update else None,
                "change_percent": update.change_percent if update else None,
                "direction": update.direction if update else None,
            }
        )
    return result


async def add_ticker(db: Database, ticker: str, user_id: str) -> dict[str, Any]:
    """Insert a ticker into the watchlist. Duplicate is a no-op."""
    symbol = _normalize(ticker)
    existing = await db.fetchone(
        "SELECT added_at FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, symbol),
    )
    if existing is not None:
        return {"ticker": symbol, "added_at": existing["added_at"]}

    added_at = _utc_iso()
    await db.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, symbol, added_at),
    )
    return {"ticker": symbol, "added_at": added_at}


async def remove_ticker(db: Database, ticker: str, user_id: str) -> None:
    """Delete a ticker from the watchlist. Raises KeyError if not present."""
    symbol = _normalize(ticker)
    row = await db.fetchone(
        "SELECT id FROM watchlist WHERE user_id = ? AND ticker = ?",
        (user_id, symbol),
    )
    if row is None:
        raise KeyError(symbol)
    await db.execute("DELETE FROM watchlist WHERE id = ?", (row["id"],))
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/watchlist/ -v
```

Expected: 7 passed.

- [ ] **Step 6: Lint + full suite**

```bash
uv run --extra dev ruff check app/ tests/
uv run --extra dev pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/watchlist backend/tests/watchlist
git commit -m "feat: add watchlist service (list/add/remove)"
```

---

## Task 6: Watchlist routes

**Files:**
- Create: `backend/app/watchlist/routes.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/watchlist/test_routes.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/watchlist/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/watchlist/test_routes.py -v
```

Expected: 404 on all endpoints (router not registered yet).

- [ ] **Step 3: Implement `backend/app/watchlist/routes.py`**

```python
"""HTTP routes for /api/watchlist."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.dependencies import get_db, get_market_source, get_price_cache
from app.market import MarketDataSource, PriceCache
from app.watchlist import service

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class TickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)


@router.get("")
async def get_watchlist(
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
) -> list[dict]:
    return await service.list_watchlist(db, cache, DEFAULT_USER_ID)


@router.post("", status_code=status.HTTP_201_CREATED)
async def add_watchlist(
    body: TickerRequest,
    db: Database = Depends(get_db),
    source: MarketDataSource = Depends(get_market_source),
) -> dict:
    try:
        entry = await service.add_ticker(db, body.ticker, DEFAULT_USER_ID)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await source.add_ticker(entry["ticker"])
    return entry


@router.delete("/{ticker}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_watchlist(
    ticker: str,
    db: Database = Depends(get_db),
    source: MarketDataSource = Depends(get_market_source),
) -> None:
    try:
        await service.remove_ticker(db, ticker, DEFAULT_USER_ID)
    except KeyError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Ticker {ticker} not in watchlist")
    await source.remove_ticker(ticker.strip().upper())
```

- [ ] **Step 4: Register router in `backend/app/main.py`**

Add the import at the top of `main.py`:

```python
from app.watchlist.routes import router as watchlist_router
```

And inside `create_app()`, after `app.include_router(health_router)`, add:

```python
    app.include_router(watchlist_router)
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/watchlist/ -v
```

Expected: 7 service tests + 5 route tests all pass.

- [ ] **Step 6: Lint + full suite**

```bash
uv run --extra dev ruff check app/ tests/
uv run --extra dev pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/watchlist/routes.py backend/app/main.py backend/tests/watchlist/test_routes.py
git commit -m "feat: add /api/watchlist GET/POST/DELETE routes"
```

---

## Task 7: Portfolio models

**Files:**
- Create: `backend/app/portfolio/__init__.py`
- Create: `backend/app/portfolio/models.py`

- [ ] **Step 1: Create `backend/app/portfolio/__init__.py`**

```python
"""Portfolio subsystem: positions, trades, valuation, snapshots."""
```

- [ ] **Step 2: Implement `backend/app/portfolio/models.py`**

```python
"""Pydantic response models for portfolio endpoints."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Position(BaseModel):
    ticker: str
    quantity: float
    avg_cost: float
    current_price: float | None
    market_value: float | None
    unrealized_pl: float | None
    unrealized_pl_percent: float | None


class PortfolioState(BaseModel):
    cash_balance: float
    total_value: float
    positions_value: float
    unrealized_pl: float
    positions: list[Position]


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class TradeResult(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float
    price: float
    executed_at: str


class Snapshot(BaseModel):
    total_value: float
    recorded_at: str
```

- [ ] **Step 3: Commit** (no tests yet — these are plain Pydantic models used by later tasks)

```bash
git add backend/app/portfolio/__init__.py backend/app/portfolio/models.py
git commit -m "feat: add portfolio Pydantic models"
```

---

## Task 8: Portfolio service — valuation

**Files:**
- Create: `backend/app/portfolio/service.py` (partial — valuation only)
- Create: `backend/tests/portfolio/__init__.py`
- Create: `backend/tests/portfolio/test_service.py` (partial)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/portfolio/__init__.py` (empty).

Create `backend/tests/portfolio/test_service.py`:

```python
"""Tests for portfolio service: valuation + trade execution."""

from __future__ import annotations

import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.market import PriceCache
from app.portfolio import service


async def test_get_portfolio_starts_empty(db: Database, price_cache: PriceCache) -> None:
    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.cash_balance == 10_000.0
    assert state.total_value == 10_000.0
    assert state.positions == []


async def _insert_position(
    db: Database, ticker: str, qty: float, avg_cost: float
) -> None:
    import uuid
    from datetime import datetime, timezone

    await db.execute(
        "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), DEFAULT_USER_ID, ticker, qty, avg_cost,
         datetime.now(timezone.utc).isoformat()),
    )


async def test_get_portfolio_with_positions(db: Database, price_cache: PriceCache) -> None:
    # AAPL seed price = 190.0 (from conftest)
    await _insert_position(db, "AAPL", 10.0, 180.0)
    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)

    assert len(state.positions) == 1
    pos = state.positions[0]
    assert pos.ticker == "AAPL"
    assert pos.quantity == 10.0
    assert pos.avg_cost == 180.0
    assert pos.current_price == 190.0
    assert pos.market_value == 1900.0
    assert pos.unrealized_pl == pytest.approx(100.0)
    assert pos.unrealized_pl_percent == pytest.approx(100.0 / 1800.0 * 100)

    assert state.positions_value == 1900.0
    assert state.total_value == 10_000.0 + 1900.0


async def test_position_without_price_has_none_valuation(db: Database) -> None:
    empty_cache = PriceCache()
    await _insert_position(db, "AAPL", 10.0, 180.0)
    state = await service.get_portfolio(db, empty_cache, DEFAULT_USER_ID)

    pos = state.positions[0]
    assert pos.current_price is None
    assert pos.market_value is None
    assert pos.unrealized_pl is None
    # Positions with no price contribute 0 to portfolio value
    assert state.total_value == 10_000.0
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/portfolio/test_service.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `backend/app/portfolio/service.py` (valuation only)**

```python
"""Portfolio valuation and trade execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db.database import Database
from app.market import PriceCache
from app.portfolio.models import PortfolioState, Position, TradeResult


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _position_from_row(row, price_cache: PriceCache) -> Position:
    update = price_cache.get(row["ticker"])
    current_price = update.price if update else None
    market_value = (current_price * row["quantity"]) if current_price is not None else None
    cost_basis = row["quantity"] * row["avg_cost"]
    if market_value is not None:
        pl = market_value - cost_basis
        pl_pct = (pl / cost_basis * 100) if cost_basis else 0.0
    else:
        pl = None
        pl_pct = None
    return Position(
        ticker=row["ticker"],
        quantity=row["quantity"],
        avg_cost=row["avg_cost"],
        current_price=current_price,
        market_value=market_value,
        unrealized_pl=pl,
        unrealized_pl_percent=pl_pct,
    )


async def get_cash_balance(db: Database, user_id: str) -> float:
    row = await db.fetchone(
        "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
    )
    return float(row["cash_balance"]) if row else 0.0


async def get_portfolio(
    db: Database, price_cache: PriceCache, user_id: str
) -> PortfolioState:
    cash = await get_cash_balance(db, user_id)
    rows = await db.fetchall(
        "SELECT ticker, quantity, avg_cost FROM positions "
        "WHERE user_id = ? AND quantity > 0 ORDER BY ticker",
        (user_id,),
    )
    positions = [_position_from_row(r, price_cache) for r in rows]
    positions_value = sum(p.market_value or 0.0 for p in positions)
    unrealized_pl = sum(p.unrealized_pl or 0.0 for p in positions)
    return PortfolioState(
        cash_balance=cash,
        total_value=cash + positions_value,
        positions_value=positions_value,
        unrealized_pl=unrealized_pl,
        positions=positions,
    )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/portfolio/test_service.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/portfolio/service.py backend/tests/portfolio
git commit -m "feat: add portfolio valuation service"
```

---

## Task 9: Portfolio service — trade execution

**Files:**
- Modify: `backend/app/portfolio/service.py`
- Modify: `backend/tests/portfolio/test_service.py`

- [ ] **Step 1: Append failing tests to `test_service.py`**

Add to `backend/tests/portfolio/test_service.py`:

```python
async def test_buy_creates_position(db: Database, price_cache: PriceCache) -> None:
    result = await service.execute_trade(
        db, price_cache, DEFAULT_USER_ID, ticker="AAPL", side="buy", quantity=5.0
    )
    assert result.ticker == "AAPL"
    assert result.side == "buy"
    assert result.price == 190.0
    assert result.quantity == 5.0

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.cash_balance == 10_000.0 - 190.0 * 5.0
    assert len(state.positions) == 1
    assert state.positions[0].quantity == 5.0
    assert state.positions[0].avg_cost == 190.0


async def test_buy_averages_cost_on_second_purchase(
    db: Database, price_cache: PriceCache
) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)
    # Mutate cache price before second buy
    price_cache.update("AAPL", 200.0)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    pos = state.positions[0]
    assert pos.quantity == 20.0
    # (10*190 + 10*200) / 20 = 195
    assert pos.avg_cost == pytest.approx(195.0)


async def test_buy_insufficient_cash_raises(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(service.InsufficientFundsError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "NVDA", "buy", 1000.0
        )


async def test_buy_unknown_ticker_raises(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(service.UnknownTickerError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "DOESNOTEXIST", "buy", 1.0
        )


async def test_sell_reduces_position(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 4.0)

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions[0].quantity == 6.0
    # Avg cost should not change on sell
    assert state.positions[0].avg_cost == 190.0
    assert state.cash_balance == 10_000.0 - 10*190.0 + 4*190.0


async def test_sell_entire_position_removes_row(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 10.0)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 10.0)

    state = await service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions == []


async def test_sell_more_than_owned_raises(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 1.0)
    with pytest.raises(service.InsufficientSharesError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 2.0
        )


async def test_sell_no_position_raises(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(service.InsufficientSharesError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "sell", 1.0
        )


async def test_trade_writes_to_trades_table(db: Database, price_cache: PriceCache) -> None:
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 3.0)
    rows = await db.fetchall("SELECT ticker, side, quantity, price FROM trades")
    assert len(rows) == 1
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["side"] == "buy"
    assert rows[0]["quantity"] == 3.0
    assert rows[0]["price"] == 190.0


async def test_trade_quantity_must_be_positive(db: Database, price_cache: PriceCache) -> None:
    with pytest.raises(ValueError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 0.0
        )
    with pytest.raises(ValueError):
        await service.execute_trade(
            db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", -1.0
        )
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/portfolio/test_service.py -v
```

Expected: 10 failures / errors — symbols `execute_trade`, `InsufficientFundsError`, etc. don't exist yet.

- [ ] **Step 3: Extend `backend/app/portfolio/service.py`**

Append to `service.py`:

```python
class TradeError(Exception):
    """Base class for trade validation errors."""


class InsufficientFundsError(TradeError):
    pass


class InsufficientSharesError(TradeError):
    pass


class UnknownTickerError(TradeError):
    pass


async def execute_trade(
    db: Database,
    price_cache: PriceCache,
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
) -> TradeResult:
    """Execute a market buy or sell at the current cache price.

    Raises:
        ValueError: if quantity <= 0 or side is invalid
        UnknownTickerError: no price available for the ticker
        InsufficientFundsError: buy exceeds cash balance
        InsufficientSharesError: sell exceeds held quantity
    """
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    if side not in ("buy", "sell"):
        raise ValueError(f"invalid side: {side}")

    symbol = ticker.strip().upper()
    update = price_cache.get(symbol)
    if update is None:
        raise UnknownTickerError(f"no price for {symbol}")
    price = update.price

    cash = await get_cash_balance(db, user_id)
    position_row = await db.fetchone(
        "SELECT id, quantity, avg_cost FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, symbol),
    )

    if side == "buy":
        cost = price * quantity
        if cost > cash:
            raise InsufficientFundsError(
                f"needs {cost:.2f}, have {cash:.2f}"
            )
        await _apply_buy(db, user_id, symbol, quantity, price, position_row)
    else:  # sell
        owned = position_row["quantity"] if position_row else 0.0
        if quantity > owned:
            raise InsufficientSharesError(f"owns {owned}, tried to sell {quantity}")
        await _apply_sell(db, user_id, symbol, quantity, price, position_row)

    now = _utc_iso()
    await db.execute(
        "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, symbol, side, quantity, price, now),
    )
    return TradeResult(
        ticker=symbol, side=side, quantity=quantity, price=price, executed_at=now
    )


async def _apply_buy(
    db: Database, user_id: str, ticker: str, qty: float, price: float, position_row
) -> None:
    now = _utc_iso()
    proceeds = price * qty
    await db.execute(
        "UPDATE users_profile SET cash_balance = cash_balance - ? WHERE id = ?",
        (proceeds, user_id),
    )
    if position_row is None:
        await db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, ticker, qty, price, now),
        )
    else:
        new_qty = position_row["quantity"] + qty
        new_avg = (
            position_row["quantity"] * position_row["avg_cost"] + qty * price
        ) / new_qty
        await db.execute(
            "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? WHERE id = ?",
            (new_qty, new_avg, now, position_row["id"]),
        )


async def _apply_sell(
    db: Database, user_id: str, ticker: str, qty: float, price: float, position_row
) -> None:
    now = _utc_iso()
    proceeds = price * qty
    await db.execute(
        "UPDATE users_profile SET cash_balance = cash_balance + ? WHERE id = ?",
        (proceeds, user_id),
    )
    new_qty = position_row["quantity"] - qty
    if new_qty <= 1e-9:
        await db.execute("DELETE FROM positions WHERE id = ?", (position_row["id"],))
    else:
        await db.execute(
            "UPDATE positions SET quantity = ?, updated_at = ? WHERE id = ?",
            (new_qty, now, position_row["id"]),
        )
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/portfolio/test_service.py -v
```

Expected: 13 passed.

- [ ] **Step 5: Lint + full suite**

```bash
uv run --extra dev ruff check app/ tests/
uv run --extra dev pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/portfolio/service.py backend/tests/portfolio/test_service.py
git commit -m "feat: add trade execution with buy/sell validation and P&L"
```

---

## Task 10: Portfolio snapshots (history helpers)

**Files:**
- Modify: `backend/app/portfolio/service.py`
- Modify: `backend/tests/portfolio/test_service.py`

- [ ] **Step 1: Append failing tests**

Add to `backend/tests/portfolio/test_service.py`:

```python
async def test_record_snapshot_writes_row(db: Database, price_cache: PriceCache) -> None:
    await service.record_snapshot(db, price_cache, DEFAULT_USER_ID)
    rows = await db.fetchall("SELECT total_value, recorded_at FROM portfolio_snapshots")
    assert len(rows) == 1
    assert rows[0]["total_value"] == 10_000.0


async def test_get_snapshots_returns_in_order(db: Database, price_cache: PriceCache) -> None:
    await service.record_snapshot(db, price_cache, DEFAULT_USER_ID)
    await service.execute_trade(db, price_cache, DEFAULT_USER_ID, "AAPL", "buy", 1.0)
    await service.record_snapshot(db, price_cache, DEFAULT_USER_ID)

    snaps = await service.get_snapshots(db, DEFAULT_USER_ID, limit=10)
    assert len(snaps) == 2
    assert snaps[0].recorded_at <= snaps[1].recorded_at
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/portfolio/test_service.py::test_record_snapshot_writes_row -v
```

Expected: `AttributeError: module 'app.portfolio.service' has no attribute 'record_snapshot'`.

- [ ] **Step 3: Extend `service.py`**

First, update the top-level import in `backend/app/portfolio/service.py` to include `Snapshot`:

Change this line:

```python
from app.portfolio.models import PortfolioState, Position, TradeResult
```

to:

```python
from app.portfolio.models import PortfolioState, Position, Snapshot, TradeResult
```

Then append to the end of `backend/app/portfolio/service.py`:

```python
async def record_snapshot(
    db: Database, price_cache: PriceCache, user_id: str
) -> Snapshot:
    """Record the current total portfolio value."""
    state = await get_portfolio(db, price_cache, user_id)
    now = _utc_iso()
    await db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, state.total_value, now),
    )
    return Snapshot(total_value=state.total_value, recorded_at=now)


async def get_snapshots(db: Database, user_id: str, limit: int = 500) -> list[Snapshot]:
    rows = await db.fetchall(
        "SELECT total_value, recorded_at FROM portfolio_snapshots "
        "WHERE user_id = ? ORDER BY recorded_at ASC LIMIT ?",
        (user_id, limit),
    )
    return [Snapshot(total_value=r["total_value"], recorded_at=r["recorded_at"]) for r in rows]
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/portfolio/test_service.py -v
```

Expected: 15 passed.

- [ ] **Step 5: Lint**

```bash
uv run --extra dev ruff check app/ tests/
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/portfolio/service.py backend/tests/portfolio/test_service.py
git commit -m "feat: add portfolio snapshot record/query helpers"
```

---

## Task 11: Portfolio routes

**Files:**
- Create: `backend/app/portfolio/routes.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/portfolio/test_routes.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/portfolio/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/portfolio/test_routes.py -v
```

Expected: all 404 (router not yet registered).

- [ ] **Step 3: Implement `backend/app/portfolio/routes.py`**

```python
"""HTTP routes for /api/portfolio."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.dependencies import get_db, get_price_cache
from app.market import PriceCache
from app.portfolio import service
from app.portfolio.models import PortfolioState, Snapshot, TradeRequest, TradeResult

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("", response_model=PortfolioState)
async def get_portfolio(
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
) -> PortfolioState:
    return await service.get_portfolio(db, cache, DEFAULT_USER_ID)


@router.post("/trade", response_model=TradeResult, status_code=status.HTTP_201_CREATED)
async def place_trade(
    body: TradeRequest,
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
) -> TradeResult:
    try:
        result = await service.execute_trade(
            db, cache, DEFAULT_USER_ID,
            ticker=body.ticker, side=body.side, quantity=body.quantity,
        )
    except (service.TradeError, ValueError) as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    # Record a snapshot immediately after trade (per PLAN.md §7)
    await service.record_snapshot(db, cache, DEFAULT_USER_ID)
    return result


@router.get("/history", response_model=list[Snapshot])
async def get_history(
    db: Database = Depends(get_db),
) -> list[Snapshot]:
    return await service.get_snapshots(db, DEFAULT_USER_ID)
```

- [ ] **Step 4: Register in `main.py`**

Add import:

```python
from app.portfolio.routes import router as portfolio_router
```

In `create_app()` add:

```python
    app.include_router(portfolio_router)
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/portfolio/test_routes.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Lint + full suite**

```bash
uv run --extra dev ruff check app/ tests/
uv run --extra dev pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/portfolio/routes.py backend/app/main.py backend/tests/portfolio/test_routes.py
git commit -m "feat: add /api/portfolio GET/trade/history routes"
```

---

## Task 12: Portfolio snapshot background task

**Files:**
- Create: `backend/app/portfolio/snapshots.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/portfolio/test_snapshots.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/portfolio/test_snapshots.py`:

```python
"""Tests for the periodic snapshot background task."""

from __future__ import annotations

import asyncio

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.market import PriceCache
from app.portfolio import service
from app.portfolio.snapshots import SnapshotTask


async def test_task_records_snapshots_on_interval(
    db: Database, price_cache: PriceCache
) -> None:
    task = SnapshotTask(db, price_cache, DEFAULT_USER_ID, interval=0.05)
    await task.start()
    await asyncio.sleep(0.18)
    await task.stop()

    snaps = await service.get_snapshots(db, DEFAULT_USER_ID)
    # Expect at least 2 snapshots in 0.18s at 0.05s interval
    assert len(snaps) >= 2


async def test_task_stop_is_idempotent(db: Database, price_cache: PriceCache) -> None:
    task = SnapshotTask(db, price_cache, DEFAULT_USER_ID, interval=0.1)
    await task.start()
    await task.stop()
    await task.stop()  # should not raise
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/portfolio/test_snapshots.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.portfolio.snapshots'`.

- [ ] **Step 3: Implement `backend/app/portfolio/snapshots.py`**

```python
"""Periodic background task that records portfolio value snapshots."""

from __future__ import annotations

import asyncio
import logging

from app.db.database import Database
from app.market import PriceCache
from app.portfolio import service

logger = logging.getLogger(__name__)


class SnapshotTask:
    """Records a portfolio snapshot every `interval` seconds.

    Lifecycle matches MarketDataSource: start() / stop(). Safe to stop twice.
    """

    def __init__(
        self,
        db: Database,
        price_cache: PriceCache,
        user_id: str,
        interval: float = 30.0,
    ) -> None:
        self._db = db
        self._cache = price_cache
        self._user_id = user_id
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._interval)
                try:
                    await service.record_snapshot(self._db, self._cache, self._user_id)
                except Exception:  # noqa: BLE001
                    logger.exception("snapshot task error")
        except asyncio.CancelledError:
            raise
```

- [ ] **Step 4: Wire into `main.py` lifespan**

Modify `main.py` — in `lifespan`, after `await source.start(tickers)`:

```python
    from app.portfolio.snapshots import SnapshotTask
    snapshot_task = SnapshotTask(db, cache, DEFAULT_USER_ID, interval=30.0)
    await snapshot_task.start()
    app.state.snapshot_task = snapshot_task
```

And in the `finally:` block, before `await source.stop()`:

```python
        await snapshot_task.stop()
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/portfolio/test_snapshots.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Lint + full suite**

```bash
uv run --extra dev ruff check app/ tests/
uv run --extra dev pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/portfolio/snapshots.py backend/app/main.py backend/tests/portfolio/test_snapshots.py
git commit -m "feat: add 30s portfolio snapshot background task"
```

---

## Task 13: Chat structured output schema

**Files:**
- Create: `backend/app/chat/__init__.py`
- Create: `backend/app/chat/models.py`

- [ ] **Step 1: Create `backend/app/chat/__init__.py`**

```python
"""Chat subsystem: LLM integration with structured outputs."""
```

- [ ] **Step 2: Implement `backend/app/chat/models.py`**

```python
"""Pydantic models for chat requests and LLM structured output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class LlmTrade(BaseModel):
    ticker: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


class LlmWatchlistChange(BaseModel):
    ticker: str
    action: Literal["add", "remove"]


class LlmResponse(BaseModel):
    """Structured output schema the LLM must produce."""

    message: str
    trades: list[LlmTrade] = Field(default_factory=list)
    watchlist_changes: list[LlmWatchlistChange] = Field(default_factory=list)


class ExecutedAction(BaseModel):
    """One row in the executed_actions payload returned to the frontend."""

    kind: Literal["trade", "watchlist_add", "watchlist_remove"]
    ticker: str
    status: Literal["ok", "error"]
    detail: str  # e.g. "bought 10 @ $190.00" or "insufficient cash"


class ChatResponse(BaseModel):
    message: str
    executed_actions: list[ExecutedAction]
```

- [ ] **Step 3: Commit** (tests come with the service that consumes these)

```bash
git add backend/app/chat/__init__.py backend/app/chat/models.py
git commit -m "feat: add chat Pydantic schemas for LLM structured outputs"
```

---

## Task 14: LLM client with mock mode

**Files:**
- Create: `backend/app/chat/llm.py`
- Create: `backend/tests/chat/__init__.py`
- Create: `backend/tests/chat/test_llm_mock.py`

**Before implementing:** this task uses the `cerebras` skill for the real-mode LLM call. Invoke it via `Skill` tool **before Step 3** to confirm the correct LiteLLM + OpenRouter + Cerebras invocation pattern. If the skill is unavailable, fall back to the pattern shown in Step 3.

- [ ] **Step 1: Write failing tests for mock mode**

Create `backend/tests/chat/__init__.py` (empty).

Create `backend/tests/chat/test_llm_mock.py`:

```python
"""Tests for the mock LLM caller (LLM_MOCK=true path)."""

from __future__ import annotations

import pytest

from app.chat.llm import call_llm_mock
from app.chat.models import LlmResponse


async def test_mock_generic_message_echoes() -> None:
    resp = await call_llm_mock(
        user_message="hello",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": []},
        history=[],
    )
    assert isinstance(resp, LlmResponse)
    assert "hello" in resp.message.lower() or resp.message
    assert resp.trades == []
    assert resp.watchlist_changes == []


async def test_mock_buy_instruction_produces_trade() -> None:
    resp = await call_llm_mock(
        user_message="buy 5 AAPL",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": ["AAPL"]},
        history=[],
    )
    assert len(resp.trades) == 1
    t = resp.trades[0]
    assert t.ticker == "AAPL"
    assert t.side == "buy"
    assert t.quantity == pytest.approx(5.0)


async def test_mock_sell_instruction_produces_trade() -> None:
    resp = await call_llm_mock(
        user_message="sell 3 TSLA",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": ["TSLA"]},
        history=[],
    )
    assert len(resp.trades) == 1
    assert resp.trades[0].side == "sell"
    assert resp.trades[0].ticker == "TSLA"


async def test_mock_add_watchlist_instruction() -> None:
    resp = await call_llm_mock(
        user_message="add PYPL to my watchlist",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": []},
        history=[],
    )
    assert len(resp.watchlist_changes) == 1
    assert resp.watchlist_changes[0].ticker == "PYPL"
    assert resp.watchlist_changes[0].action == "add"


async def test_mock_remove_watchlist_instruction() -> None:
    resp = await call_llm_mock(
        user_message="remove AAPL from watchlist",
        portfolio_context={"cash_balance": 10_000.0, "positions": [], "watchlist": ["AAPL"]},
        history=[],
    )
    assert len(resp.watchlist_changes) == 1
    assert resp.watchlist_changes[0].ticker == "AAPL"
    assert resp.watchlist_changes[0].action == "remove"
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/chat/test_llm_mock.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.chat.llm'`.

- [ ] **Step 3: Implement `backend/app/chat/llm.py`**

```python
"""LLM client: real mode via LiteLLM+OpenRouter+Cerebras, plus deterministic mock mode."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import litellm

from app.chat.models import LlmResponse, LlmTrade, LlmWatchlistChange

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant embedded in a simulated portfolio workstation.
You can analyze the user's positions, suggest trades, and execute trades and watchlist changes on their behalf.

Rules:
- Respond ONLY with a JSON object that matches the schema provided.
- The "message" field is required and holds your conversational reply.
- Populate "trades" only when the user explicitly asks you to trade or agrees to a suggestion.
- Populate "watchlist_changes" only when the user asks to add/remove a ticker.
- Be concise, data-driven, and ground every suggestion in the portfolio context provided."""


async def call_llm(
    user_message: str,
    portfolio_context: dict[str, Any],
    history: list[dict[str, str]],
    api_key: str,
) -> LlmResponse:
    """Call the LLM via LiteLLM/OpenRouter/Cerebras with structured output."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "system",
            "content": f"PORTFOLIO CONTEXT:\n{json.dumps(portfolio_context, indent=2)}",
        },
        *history,
        {"role": "user", "content": user_message},
    ]

    completion = await litellm.acompletion(
        model=MODEL,
        messages=messages,
        api_key=api_key,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "ChatResponse",
                "strict": True,
                "schema": LlmResponse.model_json_schema(),
            },
        },
        extra_body={"provider": {"order": ["Cerebras"]}},
    )
    raw = completion.choices[0].message.content or "{}"
    return LlmResponse.model_validate_json(raw)


# --- Deterministic mock for LLM_MOCK=true ----------------------------------

_BUY_RE = re.compile(r"\bbuy\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,6})\b", re.IGNORECASE)
_SELL_RE = re.compile(r"\bsell\s+(\d+(?:\.\d+)?)\s+([A-Za-z]{1,6})\b", re.IGNORECASE)
_ADD_RE = re.compile(r"\badd\s+([A-Za-z]{1,6})\b.*?\bwatch", re.IGNORECASE | re.DOTALL)
_REMOVE_RE = re.compile(
    r"\bremove\s+([A-Za-z]{1,6})\b.*?\bwatch", re.IGNORECASE | re.DOTALL
)


async def call_llm_mock(
    user_message: str,
    portfolio_context: dict[str, Any],
    history: list[dict[str, str]],
) -> LlmResponse:
    """Deterministic mock for testing. Parses simple instructions from the message."""
    trades: list[LlmTrade] = []
    changes: list[LlmWatchlistChange] = []

    for qty, ticker in _BUY_RE.findall(user_message):
        trades.append(LlmTrade(ticker=ticker.upper(), side="buy", quantity=float(qty)))
    for qty, ticker in _SELL_RE.findall(user_message):
        trades.append(LlmTrade(ticker=ticker.upper(), side="sell", quantity=float(qty)))
    for ticker in _ADD_RE.findall(user_message):
        changes.append(LlmWatchlistChange(ticker=ticker.upper(), action="add"))
    for ticker in _REMOVE_RE.findall(user_message):
        changes.append(LlmWatchlistChange(ticker=ticker.upper(), action="remove"))

    if trades or changes:
        reply = f"Acknowledged: {user_message.strip()}"
    else:
        reply = f"[MOCK] You said: {user_message.strip()}"

    return LlmResponse(message=reply, trades=trades, watchlist_changes=changes)
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/chat/test_llm_mock.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Lint**

```bash
uv run --extra dev ruff check app/ tests/
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/chat/llm.py backend/tests/chat
git commit -m "feat: add LLM client with LiteLLM+Cerebras and deterministic mock"
```

---

## Task 15: Chat service (orchestration)

**Files:**
- Create: `backend/app/chat/service.py`
- Create: `backend/tests/chat/test_service.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/chat/test_service.py`:

```python
"""Tests for chat service orchestration: context + execute + persist."""

from __future__ import annotations

import json

import pytest

from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.market import PriceCache
from app.portfolio import service as portfolio_service


class _StubSource:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.removed: list[str] = []

    async def add_ticker(self, ticker: str) -> None:
        self.added.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        self.removed.append(ticker)


@pytest.fixture
def source() -> _StubSource:
    return _StubSource()


async def test_handle_user_message_stores_both_turns(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    await service.handle_user_message(db, price_cache, source, DEFAULT_USER_ID, "hello")
    rows = await db.fetchall(
        "SELECT role, content FROM chat_messages ORDER BY created_at"
    )
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "hello"


async def test_handle_user_message_executes_trade(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    resp = await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 2 AAPL"
    )
    assert any(a.kind == "trade" and a.status == "ok" for a in resp.executed_actions)
    state = await portfolio_service.get_portfolio(db, price_cache, DEFAULT_USER_ID)
    assert state.positions[0].ticker == "AAPL"
    assert state.positions[0].quantity == 2.0


async def test_handle_user_message_failed_trade_reports_error(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    resp = await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 1000 NVDA"
    )
    assert any(a.kind == "trade" and a.status == "error" for a in resp.executed_actions)


async def test_handle_user_message_adds_watchlist(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    resp = await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "add PYPL to my watchlist"
    )
    assert any(a.kind == "watchlist_add" and a.status == "ok" for a in resp.executed_actions)
    assert "PYPL" in source.added


async def test_handle_user_message_persists_actions_json(
    db: Database, price_cache: PriceCache, source: _StubSource, monkeypatch
) -> None:
    monkeypatch.setenv("LLM_MOCK", "true")
    from app import config
    config.get_settings.cache_clear()
    from app.chat import service

    await service.handle_user_message(
        db, price_cache, source, DEFAULT_USER_ID, "buy 1 AAPL"
    )
    row = await db.fetchone(
        "SELECT actions FROM chat_messages WHERE role='assistant' ORDER BY created_at DESC LIMIT 1"
    )
    parsed = json.loads(row["actions"])
    assert isinstance(parsed, list)
    assert any(a["kind"] == "trade" for a in parsed)
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/chat/test_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.chat.service'`.

- [ ] **Step 3: Implement `backend/app/chat/service.py`**

```python
"""Chat orchestration: build context, call LLM, auto-execute actions, persist."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.config import get_settings
from app.chat import llm
from app.chat.models import ChatResponse, ExecutedAction, LlmResponse
from app.db.database import Database
from app.market import MarketDataSource, PriceCache
from app.portfolio import service as portfolio_service
from app.watchlist import service as watchlist_service

HISTORY_LIMIT = 20


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _build_portfolio_context(
    db: Database, price_cache: PriceCache, user_id: str
) -> dict[str, Any]:
    state = await portfolio_service.get_portfolio(db, price_cache, user_id)
    watchlist = await watchlist_service.list_watchlist(db, price_cache, user_id)
    return {
        "cash_balance": state.cash_balance,
        "total_value": state.total_value,
        "unrealized_pl": state.unrealized_pl,
        "positions": [p.model_dump() for p in state.positions],
        "watchlist": [w["ticker"] for w in watchlist],
    }


async def _load_history(db: Database, user_id: str) -> list[dict[str, str]]:
    rows = await db.fetchall(
        "SELECT role, content FROM chat_messages WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT ?",
        (user_id, HISTORY_LIMIT),
    )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def _execute_actions(
    db: Database,
    price_cache: PriceCache,
    market_source: MarketDataSource,
    user_id: str,
    llm_response: LlmResponse,
) -> list[ExecutedAction]:
    executed: list[ExecutedAction] = []

    for trade in llm_response.trades:
        try:
            result = await portfolio_service.execute_trade(
                db, price_cache, user_id,
                ticker=trade.ticker, side=trade.side, quantity=trade.quantity,
            )
            executed.append(ExecutedAction(
                kind="trade", ticker=result.ticker, status="ok",
                detail=f"{result.side} {result.quantity} @ ${result.price:.2f}",
            ))
            await portfolio_service.record_snapshot(db, price_cache, user_id)
        except (portfolio_service.TradeError, ValueError) as e:
            executed.append(ExecutedAction(
                kind="trade", ticker=trade.ticker, status="error", detail=str(e),
            ))

    for change in llm_response.watchlist_changes:
        if change.action == "add":
            try:
                entry = await watchlist_service.add_ticker(db, change.ticker, user_id)
                await market_source.add_ticker(entry["ticker"])
                executed.append(ExecutedAction(
                    kind="watchlist_add", ticker=entry["ticker"],
                    status="ok", detail="added",
                ))
            except ValueError as e:
                executed.append(ExecutedAction(
                    kind="watchlist_add", ticker=change.ticker,
                    status="error", detail=str(e),
                ))
        else:  # remove
            try:
                await watchlist_service.remove_ticker(db, change.ticker, user_id)
                await market_source.remove_ticker(change.ticker.strip().upper())
                executed.append(ExecutedAction(
                    kind="watchlist_remove", ticker=change.ticker.upper(),
                    status="ok", detail="removed",
                ))
            except (KeyError, ValueError) as e:
                executed.append(ExecutedAction(
                    kind="watchlist_remove", ticker=change.ticker,
                    status="error", detail=str(e),
                ))

    return executed


async def _store(db: Database, user_id: str, role: str, content: str,
                 actions: list[ExecutedAction] | None = None) -> None:
    actions_json = json.dumps([a.model_dump() for a in actions]) if actions else None
    await db.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, role, content, actions_json, _utc_iso()),
    )


async def handle_user_message(
    db: Database,
    price_cache: PriceCache,
    market_source: MarketDataSource,
    user_id: str,
    user_message: str,
) -> ChatResponse:
    settings = get_settings()
    context = await _build_portfolio_context(db, price_cache, user_id)
    history = await _load_history(db, user_id)

    await _store(db, user_id, "user", user_message)

    if settings.llm_mock:
        llm_resp = await llm.call_llm_mock(user_message, context, history)
    else:
        llm_resp = await llm.call_llm(
            user_message, context, history, settings.openrouter_api_key
        )

    executed = await _execute_actions(
        db, price_cache, market_source, user_id, llm_resp
    )

    await _store(db, user_id, "assistant", llm_resp.message, executed)
    return ChatResponse(message=llm_resp.message, executed_actions=executed)
```

- [ ] **Step 4: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/chat/test_service.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Lint + full suite**

```bash
uv run --extra dev ruff check app/ tests/
uv run --extra dev pytest -q
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/chat/service.py backend/tests/chat/test_service.py
git commit -m "feat: add chat service orchestration with auto-execute"
```

---

## Task 16: Chat route

**Files:**
- Create: `backend/app/chat/routes.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/chat/test_routes.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/chat/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests, confirm failure**

```bash
uv run --extra dev pytest tests/chat/test_routes.py -v
```

Expected: all 404 (router not registered).

- [ ] **Step 3: Implement `backend/app/chat/routes.py`**

```python
"""HTTP route for /api/chat."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.chat import service
from app.chat.models import ChatRequest, ChatResponse
from app.db.database import Database
from app.db.seed_data import DEFAULT_USER_ID
from app.dependencies import get_db, get_market_source, get_price_cache
from app.market import MarketDataSource, PriceCache

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    db: Database = Depends(get_db),
    cache: PriceCache = Depends(get_price_cache),
    source: MarketDataSource = Depends(get_market_source),
) -> ChatResponse:
    return await service.handle_user_message(
        db, cache, source, DEFAULT_USER_ID, body.message
    )
```

- [ ] **Step 4: Register in `main.py`**

Add import:

```python
from app.chat.routes import router as chat_router
```

In `create_app()`:

```python
    app.include_router(chat_router)
```

- [ ] **Step 5: Run tests, confirm pass**

```bash
uv run --extra dev pytest tests/chat/test_routes.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Lint + full suite**

```bash
uv run --extra dev ruff check app/ tests/
uv run --extra dev pytest -q
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/chat/routes.py backend/app/main.py backend/tests/chat/test_routes.py
git commit -m "feat: add /api/chat route"
```

---

## Task 17: End-to-end smoke test

**Files:**
- Modify: `backend/tests/test_main.py`

- [ ] **Step 1: Append a full-flow smoke test**

Append to `backend/tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run test, confirm pass**

```bash
uv run --extra dev pytest tests/test_main.py::test_smoke_full_flow -v
```

Expected: 1 passed.

- [ ] **Step 3: Full suite + lint**

```bash
uv run --extra dev pytest -q
uv run --extra dev ruff check app/ tests/
```

Expected: all tests pass, no lint errors.

- [ ] **Step 4: Manual uvicorn smoke test**

Start the server and hit it:

```bash
FINALLY_DB_PATH=/tmp/finally-smoke.db LLM_MOCK=true uv run uvicorn app.main:create_app --factory --port 8001 &
sleep 2
curl -s http://localhost:8001/api/health
curl -s http://localhost:8001/api/watchlist | head -c 200
curl -s http://localhost:8001/api/portfolio
curl -s -X POST http://localhost:8001/api/chat -H 'content-type: application/json' -d '{"message":"buy 1 AAPL"}'
kill %1
rm -f /tmp/finally-smoke.db
```

Expected outputs:
- `/api/health` → `{"status":"ok"}`
- `/api/watchlist` → JSON array with 10 seeded tickers
- `/api/portfolio` → `{"cash_balance":10000.0,...}`
- `/api/chat` → JSON with `executed_actions`

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_main.py
git commit -m "test: add end-to-end smoke test for full API surface"
```

---

## Task 18: Documentation sweep

**Files:**
- Modify: `backend/CLAUDE.md`

- [ ] **Step 1: Update `backend/CLAUDE.md`**

Append a new section after the existing Market Data API section:

```markdown
## REST API (Portfolio / Watchlist / Chat)

All endpoints live under `/api/*` and are mounted in `app.main.create_app()`. Shared state (DB, PriceCache, MarketDataSource) is attached to `app.state` in the lifespan handler and read via dependency functions in `app/dependencies.py`.

### Services

- `app/watchlist/service.py` — `list_watchlist`, `add_ticker`, `remove_ticker`
- `app/portfolio/service.py` — `get_portfolio`, `execute_trade`, `record_snapshot`, `get_snapshots`, plus exception types `TradeError`, `InsufficientFundsError`, `InsufficientSharesError`, `UnknownTickerError`
- `app/chat/service.py` — `handle_user_message` (builds context, calls LLM, auto-executes trades/watchlist changes, persists conversation)

### LLM Modes

- `LLM_MOCK=true` → `app.chat.llm.call_llm_mock` (regex-based deterministic responses)
- Otherwise → `app.chat.llm.call_llm` (LiteLLM + OpenRouter + Cerebras, structured output via `LlmResponse`)

### Background Tasks

- `SnapshotTask` in `app/portfolio/snapshots.py` records `portfolio_snapshots` every 30 s.
- The market data source writes live prices to the shared `PriceCache`.

### Running the server

```bash
cd backend
uv run uvicorn app.main:create_app --factory --port 8000
```
```

- [ ] **Step 2: Commit**

```bash
git add backend/CLAUDE.md
git commit -m "docs: document REST API structure in backend CLAUDE.md"
```

---

## Final Verification

Before declaring the plan complete, from `backend/`:

```bash
uv run --extra dev pytest -v
uv run --extra dev pytest --cov=app --cov-report=term-missing
uv run --extra dev ruff check app/ tests/
```

Expected:
- All tests pass (73 existing market tests + the ~50 new ones = ~120+)
- Coverage ≥80% on every module outside `app/market/massive_client.py` (which is test-mocked for the real API)
- No lint errors

Then verify the API is usable manually, exactly as the frontend will use it:

```bash
FINALLY_DB_PATH=/tmp/finally.db LLM_MOCK=true uv run uvicorn app.main:create_app --factory
```

Open another terminal:

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/watchlist
curl http://localhost:8000/api/portfolio
curl -N http://localhost:8000/api/stream/prices   # should stream SSE events
```

If all four respond cleanly, the backend is ready for the frontend to integrate against.

---

## Notes for the Implementing Agent

1. **Commit per task, not per step.** Each task is one logical unit that ends in green tests.
2. **If a test unexpectedly passes at Step 2** (the "confirm failure" step), something is wrong — investigate before continuing.
3. **If you need to add a dependency**, use `uv add <pkg>`; do not hand-edit `pyproject.toml`'s dependencies array.
4. **If `uv run` fails with "no such option"**, ensure you added `--extra dev` for commands that need dev dependencies (pytest, ruff).
5. **Never skip the lint step** — ruff errors surface issues that would fail CI.
6. **The `app/market/` package is off-limits** for modifications. If you need something from it, use its public API (`from app.market import ...`).
7. **When the plan says "Create X", create it exactly as shown.** When it says "Modify Y", apply the diff shown (usually an import + a line in `create_app()`).
8. **Ruff config:** the project uses `line-length=100`, ignores `E501`, selects `E,F,I,N,W`. If a legitimate code path requires a noqa (e.g. the late import in Task 10), include it inline with the specific rule code.
