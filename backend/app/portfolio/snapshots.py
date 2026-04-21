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
