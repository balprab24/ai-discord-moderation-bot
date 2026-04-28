"""SQLite audit log repository."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import List, Optional

from .models import AuditEvent


SCHEMA = """
CREATE TABLE IF NOT EXISTS moderation_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    guild_id TEXT,
    channel_id TEXT,
    user_id TEXT,
    content_type TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence REAL NOT NULL,
    latency_ms REAL NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_moderation_audit_created_at
    ON moderation_audit(created_at DESC);
"""


class AuditLogRepository:
    """Async-friendly repository backed by SQLite."""

    def __init__(self, database_path: str = "moderation.db"):
        self.database_path = database_path
        self._initialized = False
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await asyncio.to_thread(self._initialize_sync)
            self._initialized = True

    async def record(self, event: AuditEvent) -> int:
        await self.initialize()
        return await asyncio.to_thread(self._record_sync, event)

    async def list_recent(self, limit: int = 25) -> List[AuditEvent]:
        await self.initialize()
        return await asyncio.to_thread(self._list_recent_sync, max(1, limit))

    async def count(self) -> int:
        await self.initialize()
        return await asyncio.to_thread(self._count_sync)

    def _connect(self) -> sqlite3.Connection:
        if self.database_path != ":memory:":
            path = Path(self.database_path)
            if path.parent and str(path.parent) not in ("", "."):
                path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_sync(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _record_sync(self, event: AuditEvent) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO moderation_audit (
                    message_id, guild_id, channel_id, user_id, content_type,
                    action, reason, confidence, latency_ms, category, source,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.message_id,
                    event.guild_id,
                    event.channel_id,
                    event.user_id,
                    event.content_type,
                    event.action,
                    event.reason,
                    event.confidence,
                    event.latency_ms,
                    event.category,
                    event.source,
                    event.created_at,
                ),
            )
            return int(cursor.lastrowid)

    def _list_recent_sync(self, limit: int) -> List[AuditEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM moderation_audit
                ORDER BY datetime(created_at) DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]

    def _count_sync(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM moderation_audit").fetchone()
        return int(row["count"])


def _row_to_event(row: sqlite3.Row) -> AuditEvent:
    return AuditEvent(
        id=int(row["id"]),
        message_id=row["message_id"],
        guild_id=row["guild_id"],
        channel_id=row["channel_id"],
        user_id=row["user_id"],
        content_type=row["content_type"],
        action=row["action"],
        reason=row["reason"],
        confidence=float(row["confidence"]),
        latency_ms=float(row["latency_ms"]),
        category=row["category"],
        source=row["source"],
        created_at=row["created_at"],
    )

