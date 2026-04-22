"""Chat orchestration: build context, call LLM, propose or execute actions, persist."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.chat import llm
from app.chat.models import (
    ChatResponse,
    ExecutedAction,
    LlmResponse,
    ProposedAction,
    ProposedTrade,
    ProposedWatchlistChange,
)
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


def _llm_response_to_proposed(resp: LlmResponse) -> list[ProposedAction]:
    """Convert the LLM's structured output into client-facing proposed actions."""
    proposed: list[ProposedAction] = []
    for t in resp.trades:
        proposed.append(
            ProposedTrade(
                kind="trade",
                ticker=t.ticker.upper(),
                side=t.side,
                quantity=t.quantity,
            )
        )
    for w in resp.watchlist_changes:
        proposed.append(
            ProposedWatchlistChange(
                kind="watchlist_add" if w.action == "add" else "watchlist_remove",
                ticker=w.ticker.upper(),
            )
        )
    return proposed


async def _execute_proposed(
    db: Database,
    price_cache: PriceCache,
    market_source: MarketDataSource,
    user_id: str,
    actions: list[ProposedAction],
) -> list[ExecutedAction]:
    """Run a list of proposed actions, collecting per-action results."""
    executed: list[ExecutedAction] = []
    for action in actions:
        if isinstance(action, ProposedTrade):
            try:
                result = await portfolio_service.execute_trade(
                    db,
                    price_cache,
                    user_id,
                    ticker=action.ticker,
                    side=action.side,
                    quantity=action.quantity,
                )
                executed.append(
                    ExecutedAction(
                        kind="trade",
                        ticker=result.ticker,
                        status="ok",
                        detail=f"{result.side} {result.quantity} @ ${result.price:.2f}",
                    )
                )
                await portfolio_service.record_snapshot(db, price_cache, user_id)
            except (portfolio_service.TradeError, ValueError) as e:
                executed.append(
                    ExecutedAction(
                        kind="trade",
                        ticker=action.ticker,
                        status="error",
                        detail=str(e),
                    )
                )
        elif action.kind == "watchlist_add":
            try:
                entry = await watchlist_service.add_ticker(
                    db, action.ticker, user_id
                )
                await market_source.add_ticker(entry["ticker"])
                executed.append(
                    ExecutedAction(
                        kind="watchlist_add",
                        ticker=entry["ticker"],
                        status="ok",
                        detail="added",
                    )
                )
            except ValueError as e:
                executed.append(
                    ExecutedAction(
                        kind="watchlist_add",
                        ticker=action.ticker,
                        status="error",
                        detail=str(e),
                    )
                )
        else:  # watchlist_remove
            symbol = action.ticker.strip().upper()
            try:
                await watchlist_service.remove_ticker(db, symbol, user_id)
                await market_source.remove_ticker(symbol)
                executed.append(
                    ExecutedAction(
                        kind="watchlist_remove",
                        ticker=symbol,
                        status="ok",
                        detail="removed",
                    )
                )
            except (KeyError, ValueError) as e:
                executed.append(
                    ExecutedAction(
                        kind="watchlist_remove",
                        ticker=action.ticker,
                        status="error",
                        detail=str(e),
                    )
                )
    return executed


def _summarize_execution(executed: list[ExecutedAction]) -> str:
    if not executed:
        return "No actions to execute."
    ok = sum(1 for a in executed if a.status == "ok")
    err = len(executed) - ok
    if err == 0:
        return f"Executed {ok} action(s)."
    if ok == 0:
        return f"All {err} action(s) failed."
    return f"Executed {ok} action(s) with {err} error(s)."


async def _insert_message(
    conn,
    user_id: str,
    role: str,
    content: str,
    actions: list[ExecutedAction] | None = None,
) -> None:
    actions_json = json.dumps([a.model_dump() for a in actions]) if actions else None
    await conn.execute(
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
    confirm_actions: list[ProposedAction] | None = None,
) -> ChatResponse:
    """Handle one chat turn.

    - If `confirm_actions` is non-empty, execute them directly (confirmation
      turn), skip the LLM, and return executed results.
    - Otherwise, call the LLM, return its proposals WITHOUT executing them,
      and let the client confirm on a subsequent turn.
    """
    if confirm_actions:
        executed = await _execute_proposed(
            db, price_cache, market_source, user_id, confirm_actions
        )
        reply = _summarize_execution(executed)
        async with db.transaction() as conn:
            await _insert_message(conn, user_id, "user", user_message)
            await _insert_message(conn, user_id, "assistant", reply, executed)
        return ChatResponse(
            message=reply, proposed_actions=[], executed_actions=executed
        )

    settings = get_settings()
    context = await _build_portfolio_context(db, price_cache, user_id)
    history = await _load_history(db, user_id)

    if settings.llm_mock:
        llm_resp = await llm.call_llm_mock(user_message, context, history)
    else:
        llm_resp = await llm.call_llm(
            user_message, context, history, settings.openrouter_api_key
        )

    proposed = _llm_response_to_proposed(llm_resp)

    async with db.transaction() as conn:
        await _insert_message(conn, user_id, "user", user_message)
        await _insert_message(conn, user_id, "assistant", llm_resp.message)

    return ChatResponse(
        message=llm_resp.message,
        proposed_actions=proposed,
        executed_actions=[],
    )
