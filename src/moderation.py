"""Moderation service coordinating text, image, rate limiting, and audit logs."""

from __future__ import annotations

import time
from typing import Optional

from .audit import AuditLogRepository
from .config import Settings
from .image_classifier import ImageClassifier
from .models import (
    AuditEvent,
    ModerationContext,
    ModerationDecision,
    action_for_score,
)
from .rate_limiter import RateLimiter
from .text_moderator import analyze_text


class ModerationService:
    """Facade used by Discord, REST, tests, and the offline demo."""

    def __init__(
        self,
        audit_log: AuditLogRepository,
        image_classifier: ImageClassifier,
        rate_limiter: RateLimiter,
        threshold: float = 0.75,
    ) -> None:
        self.audit_log = audit_log
        self.image_classifier = image_classifier
        self.rate_limiter = rate_limiter
        self.threshold = threshold

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModerationService":
        return cls(
            audit_log=AuditLogRepository(settings.database_path),
            image_classifier=ImageClassifier(
                settings.nsfw_model_path,
                threshold=settings.moderation_threshold,
            ),
            rate_limiter=RateLimiter(
                max_concurrent=settings.max_concurrent_tasks,
                min_interval_seconds=settings.min_api_interval_seconds,
            ),
            threshold=settings.moderation_threshold,
        )

    async def initialize(self) -> None:
        await self.audit_log.initialize()

    async def moderate_text(
        self,
        content: str,
        context: Optional[ModerationContext] = None,
        persist: bool = True,
    ) -> ModerationDecision:
        context = context or ModerationContext()
        start = time.perf_counter()
        analysis = await self.rate_limiter.call(analyze_text, content)
        latency_ms = (time.perf_counter() - start) * 1000
        decision = ModerationDecision(
            message_id=context.message_id,
            content_type="text",
            action=action_for_score(analysis.score, self.threshold),
            confidence=analysis.score,
            reason=analysis.reason,
            latency_ms=latency_ms,
            category=analysis.category,
            source="local_text_rules",
        )
        if persist:
            await self.audit_log.record(AuditEvent.from_decision(decision, context))
        return decision

    async def moderate_image(
        self,
        image_bytes: bytes,
        filename: str = "attachment",
        context: Optional[ModerationContext] = None,
        persist: bool = True,
    ) -> ModerationDecision:
        context = context or ModerationContext()
        start = time.perf_counter()
        classification = await self.rate_limiter.call(
            self.image_classifier.classify, image_bytes, filename
        )
        latency_ms = (time.perf_counter() - start) * 1000
        decision = ModerationDecision(
            message_id=context.message_id,
            content_type="image",
            action=action_for_score(classification.score, self.threshold),
            confidence=classification.score,
            reason=classification.reason,
            latency_ms=latency_ms,
            category=classification.label,
            source="pytorch_image_model"
            if classification.model_loaded
            else "deterministic_image_fallback",
        )
        if persist:
            await self.audit_log.record(AuditEvent.from_decision(decision, context))
        return decision

