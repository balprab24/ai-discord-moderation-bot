import asyncio
import time

import pytest

from src.audit import AuditLogRepository
from src.models import AuditEvent
from src.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_audit_log_records_and_lists_events(tmp_path):
    audit = AuditLogRepository(str(tmp_path / "audit.db"))
    event_id = await audit.record(
        AuditEvent(
            message_id="msg-1",
            guild_id="guild",
            channel_id="channel",
            user_id="user",
            content_type="text",
            action="delete",
            reason="matched demo rule",
            confidence=0.9,
            latency_ms=12.5,
            category="spam",
            source="test",
            created_at="2025-10-01T00:00:00+00:00",
        )
    )

    rows = await audit.list_recent()
    assert event_id > 0
    assert len(rows) == 1
    assert rows[0].message_id == "msg-1"


@pytest.mark.asyncio
async def test_rate_limiter_paces_calls():
    limiter = RateLimiter(max_concurrent=2, min_interval_seconds=0.02)
    starts = []

    async def task(index):
        starts.append((index, time.perf_counter()))
        await asyncio.sleep(0)
        return index

    results = await asyncio.gather(*(limiter.call(task, i) for i in range(3)))

    assert results == [0, 1, 2]
    starts.sort()
    assert starts[1][1] - starts[0][1] >= 0.015

