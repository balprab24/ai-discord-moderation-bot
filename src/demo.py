"""Offline recruiter demo for the Discord moderation pipeline."""

from __future__ import annotations

import asyncio
from typing import Dict, List

from .audit import AuditLogRepository
from .config import Settings
from .image_classifier import ImageClassifier
from .models import ModerationContext
from .moderation import ModerationService
from .rate_limiter import RateLimiter


def build_demo_service(database_url: str = "sqlite:///demo_moderation.db") -> ModerationService:
    settings = Settings.from_env()
    demo_settings = Settings(
        discord_token=settings.discord_token,
        database_url=database_url,
        nsfw_model_path=settings.nsfw_model_path,
        moderation_threshold=settings.moderation_threshold,
        max_concurrent_tasks=settings.max_concurrent_tasks,
        min_api_interval_seconds=0.0,
        api_host=settings.api_host,
        api_port=settings.api_port,
        audit_fetch_limit=settings.audit_fetch_limit,
    )
    return ModerationService(
        audit_log=AuditLogRepository(demo_settings.database_path),
        image_classifier=ImageClassifier(
            demo_settings.nsfw_model_path,
            threshold=demo_settings.moderation_threshold,
        ),
        rate_limiter=RateLimiter(
            max_concurrent=demo_settings.max_concurrent_tasks,
            min_interval_seconds=demo_settings.min_api_interval_seconds,
        ),
        threshold=demo_settings.moderation_threshold,
    )


async def run_demo(
    database_url: str = "sqlite:///demo_moderation.db", emit: bool = True
) -> Dict[str, object]:
    service = build_demo_service(database_url)
    await service.initialize()
    starting_audit_count = await service.audit_log.count()

    text_samples = [
        ("demo-msg-001", "Hey team, are we still meeting at 5?"),
        ("demo-msg-002", "@everyone free nitro giveaway winner click this link https://bit.ly/prize"),
        ("demo-msg-003", "Please verify your wallet seed phrase in this account recovery form"),
    ]
    image_samples = [
        ("demo-img-001", "cat-photo.jpg", b"DEMO_SAFE pretend image bytes"),
        ("demo-img-002", "upload-nsfw.png", b"DEMO_NSFW pretend image bytes"),
    ]

    decisions: List[Dict[str, object]] = []
    for message_id, content in text_samples:
        decision = await service.moderate_text(
            content,
            context=ModerationContext(
                message_id=message_id,
                guild_id="demo-guild",
                channel_id="demo-channel",
                user_id="demo-user",
            ),
        )
        decisions.append(decision.to_dict())
        if emit:
            _print_decision(decision.to_dict())

    for message_id, filename, image_bytes in image_samples:
        decision = await service.moderate_image(
            image_bytes,
            filename=filename,
            context=ModerationContext(
                message_id=message_id,
                guild_id="demo-guild",
                channel_id="demo-channel",
                user_id="demo-user",
            ),
        )
        decisions.append(decision.to_dict())
        if emit:
            _print_decision(decision.to_dict())

    total_audit_count = await service.audit_log.count()
    audit_count = total_audit_count - starting_audit_count
    if emit:
        print(f"\nAudit events recorded this run: {audit_count}")
        print(f"Total audit events in database: {total_audit_count}")
        print(f"Latency target: under 500ms per message in demo mode")
    return {
        "decisions": decisions,
        "audit_count": audit_count,
        "total_audit_count": total_audit_count,
    }


def _print_decision(decision: Dict[str, object]) -> None:
    print(
        f"[{str(decision['action']).upper():6}] "
        f"{decision['content_type']} "
        f"score={float(decision['confidence']):.2f} "
        f"latency={float(decision['latency_ms']):.2f}ms "
        f"reason={decision['reason']}"
    )


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
