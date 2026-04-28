import pytest

from src.audit import AuditLogRepository
from src.image_classifier import ImageClassifier
from src.models import ALLOW, DELETE, FLAG, ModerationContext
from src.moderation import ModerationService
from src.rate_limiter import RateLimiter


def make_service(tmp_path):
    return ModerationService(
        audit_log=AuditLogRepository(str(tmp_path / "audit.db")),
        image_classifier=ImageClassifier(threshold=0.75),
        rate_limiter=RateLimiter(max_concurrent=4, min_interval_seconds=0),
        threshold=0.75,
    )


@pytest.mark.asyncio
async def test_clean_text_is_allowed_and_audited(tmp_path):
    service = make_service(tmp_path)
    decision = await service.moderate_text(
        "Normal project discussion for the server.",
        context=ModerationContext(message_id="clean-1"),
    )

    assert decision.action == ALLOW
    assert decision.confidence < 0.35
    assert await service.audit_log.count() == 1


@pytest.mark.asyncio
async def test_spam_text_is_deleted(tmp_path):
    service = make_service(tmp_path)
    decision = await service.moderate_text(
        "@everyone free nitro giveaway winner click this link https://bit.ly/prize",
        context=ModerationContext(message_id="spam-1"),
    )

    assert decision.action == DELETE
    assert decision.category == "spam"
    assert decision.latency_ms < 500


@pytest.mark.asyncio
async def test_mid_confidence_text_is_flagged(tmp_path):
    service = make_service(tmp_path)
    decision = await service.moderate_text(
        "Please keep this nsfw discussion out of the main server.",
        context=ModerationContext(message_id="flag-1"),
    )

    assert decision.action == FLAG

