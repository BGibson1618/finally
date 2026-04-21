# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync --extra dev   # Install all dependencies including test/lint tools
```

## Market Data API

The market data subsystem lives in `app/market/`. Use these imports:

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source
```

### Core Types

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `timestamp`, plus properties `change`, `change_percent`, `direction` ("up"/"down"/"flat"), and `to_dict()` for JSON serialization.

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None) -> PriceUpdate`
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `remove(ticker)`
  - `version` property — monotonic counter, increments on every update (for SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource` and `MassiveDataSource`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`.

- **`create_market_data_source(cache)`** — Factory. Returns `MassiveDataSource` if `MASSIVE_API_KEY` is set, otherwise `SimulatorDataSource`.

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # Returns FastAPI APIRouter
# Endpoint: GET /api/stream/prices (text/event-stream)
```

### Seed Data

Default tickers: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX. Seed prices and per-ticker volatility/drift params are in `app/market/seed_prices.py`.

## Running Tests

```bash
uv run --extra dev pytest -v              # All tests
uv run --extra dev pytest --cov=app       # With coverage
uv run --extra dev ruff check app/ tests/ # Lint
```

## Demo

```bash
uv run market_data_demo.py   # Live terminal dashboard with simulated prices
```

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
