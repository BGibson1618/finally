"""Chat orchestration: build context, call LLM, auto-execute actions, persist."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.chat import llm
from app.chat.models import ChatResponse, ExecutedAction, LlmResponse
from app.config import get_settings
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
