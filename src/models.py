"""Shared data models for moderation decisions and audit events."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4


ALLOW = "allow"
FLAG = "flag"
DELETE = "delete"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def action_for_score(score: float, threshold: float) -> str:
    if score >= threshold:
        return DELETE
    if score >= max(0.35, threshold * 0.6):
        return FLAG
    return ALLOW


@dataclass(frozen=True)
class ModerationContext:
    """Discord/API context attached to a moderation check."""

    message_id: str = field(default_factory=lambda: f"local-{uuid4().hex[:12]}")
    guild_id: Optional[str] = None
    channel_id: Optional[str] = None
    user_id: Optional[str] = None

    @classmethod
    def from_mapping(cls, payload: Optional[Dict[str, Any]]) -> "ModerationContext":
        if not payload:
            return cls()
        return cls(
            message_id=str(payload.get("message_id") or f"api-{uuid4().hex[:12]}"),
            guild_id=_optional_str(payload.get("guild_id")),
            channel_id=_optional_str(payload.get("channel_id")),
            user_id=_optional_str(payload.get("user_id")),
        )

    @classmethod
    def from_discord_message(cls, message: Any) -> "ModerationContext":
        guild = getattr(message, "guild", None)
        channel = getattr(message, "channel", None)
        author = getattr(message, "author", None)
        return cls(
            message_id=str(getattr(message, "id", f"discord-{uuid4().hex[:12]}")),
            guild_id=_optional_str(getattr(guild, "id", None)),
            channel_id=_optional_str(getattr(channel, "id", None)),
            user_id=_optional_str(getattr(author, "id", None)),
        )


@dataclass(frozen=True)
class ModerationDecision:
    """Normalized moderation result returned by every interface."""

    message_id: str
    content_type: str
    action: str
    confidence: float
    reason: str
    latency_ms: float
    category: str
    source: str
    created_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["confidence"] = round(float(self.confidence), 3)
        data["latency_ms"] = round(float(self.latency_ms), 2)
        return data


@dataclass(frozen=True)
class AuditEvent:
    """Database representation of a moderation decision."""

    message_id: str
    guild_id: Optional[str]
    channel_id: Optional[str]
    user_id: Optional[str]
    content_type: str
    action: str
    reason: str
    confidence: float
    latency_ms: float
    category: str
    source: str
    created_at: str
    id: Optional[int] = None

    @classmethod
    def from_decision(
        cls, decision: ModerationDecision, context: ModerationContext
    ) -> "AuditEvent":
        return cls(
            message_id=decision.message_id,
            guild_id=context.guild_id,
            channel_id=context.channel_id,
            user_id=context.user_id,
            content_type=decision.content_type,
            action=decision.action,
            reason=decision.reason,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            category=decision.category,
            source=decision.source,
            created_at=decision.created_at,
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["confidence"] = round(float(self.confidence), 3)
        data["latency_ms"] = round(float(self.latency_ms), 2)
        return data


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)

