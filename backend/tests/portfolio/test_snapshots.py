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
