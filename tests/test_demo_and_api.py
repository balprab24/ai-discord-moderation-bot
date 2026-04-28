import base64

import pytest

from src.demo import run_demo


@pytest.mark.asyncio
async def test_demo_records_audit_events(tmp_path):
    summary = await run_demo(
        database_url=f"sqlite:///{tmp_path / 'demo.db'}",
        emit=False,
    )

    assert summary["audit_count"] == 5
    assert any(
        decision["action"] == "delete"
        for decision in summary["decisions"]
    )


@pytest.mark.asyncio
async def test_api_health_text_image_and_audit(tmp_path):
    pytest.importorskip("aiohttp")
    from aiohttp.test_utils import TestClient, TestServer

    from src.api import create_app
    from src.audit import AuditLogRepository
    from src.config import Settings
    from src.image_classifier import ImageClassifier
    from src.moderation import ModerationService
    from src.rate_limiter import RateLimiter

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'api.db'}")
    service = ModerationService(
        audit_log=AuditLogRepository(settings.database_path),
        image_classifier=ImageClassifier(threshold=settings.moderation_threshold),
        rate_limiter=RateLimiter(max_concurrent=4),
        threshold=settings.moderation_threshold,
    )
    app = create_app(settings=settings, service=service)

    async with TestClient(TestServer(app)) as client:
        health = await client.get("/health")
        assert health.status == 200
        health_json = await health.json()
        assert health_json["status"] == "ok"

        text = await client.post(
            "/moderate/text",
            json={
                "content": "free nitro giveaway winner click this link https://bit.ly/prize",
                "context": {"message_id": "api-text-1"},
            },
        )
        assert text.status == 200
        text_json = await text.json()
        assert text_json["action"] == "delete"

        image = await client.post(
            "/moderate/image",
            json={
                "filename": "upload.png",
                "image_base64": base64.b64encode(b"DEMO_NSFW bytes").decode("ascii"),
                "context": {"message_id": "api-img-1"},
            },
        )
        assert image.status == 200
        image_json = await image.json()
        assert image_json["action"] == "delete"

        audit = await client.get("/audit")
        assert audit.status == 200
        audit_json = await audit.json()
        assert len(audit_json["events"]) == 2

