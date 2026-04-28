import pytest

from src.image_classifier import ImageClassifier
from src.models import ALLOW, DELETE, ModerationContext
from src.moderation import ModerationService
from src.audit import AuditLogRepository
from src.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_image_classifier_demo_safe_marker():
    classifier = ImageClassifier(threshold=0.75)
    result = await classifier.classify(b"DEMO_SAFE image bytes", "safe.png")

    assert result.label == "safe"
    assert result.score < 0.75
    assert not result.model_loaded


@pytest.mark.asyncio
async def test_image_classifier_demo_nsfw_marker():
    classifier = ImageClassifier(threshold=0.75)
    result = await classifier.classify(b"DEMO_NSFW image bytes", "upload.png")

    assert result.label == "nsfw"
    assert result.score >= 0.75


@pytest.mark.asyncio
async def test_image_moderation_is_audited(tmp_path):
    service = ModerationService(
        audit_log=AuditLogRepository(str(tmp_path / "audit.db")),
        image_classifier=ImageClassifier(threshold=0.75),
        rate_limiter=RateLimiter(max_concurrent=2),
        threshold=0.75,
    )

    decision = await service.moderate_image(
        b"DEMO_NSFW bytes",
        filename="upload.png",
        context=ModerationContext(message_id="img-1"),
    )

    assert decision.action == DELETE
    assert await service.audit_log.count() == 1


@pytest.mark.asyncio
async def test_empty_image_is_allowed(tmp_path):
    service = ModerationService(
        audit_log=AuditLogRepository(str(tmp_path / "audit.db")),
        image_classifier=ImageClassifier(threshold=0.75),
        rate_limiter=RateLimiter(max_concurrent=2),
        threshold=0.75,
    )

    decision = await service.moderate_image(
        b"",
        context=ModerationContext(message_id="empty-img"),
    )

    assert decision.action == ALLOW

