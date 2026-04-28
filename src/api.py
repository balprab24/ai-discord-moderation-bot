"""Small aiohttp REST API for moderation and audit lookup."""

from __future__ import annotations

import base64
import binascii
from typing import Any, Dict

from .config import Settings
from .models import ModerationContext
from .moderation import ModerationService

try:
    from aiohttp import web
except ImportError:  # pragma: no cover - exercised only without optional deps
    web = None


def create_app(
    settings: Settings = None, service: ModerationService = None
) -> "web.Application":
    if web is None:
        raise RuntimeError("aiohttp is required for the REST API. Install requirements.txt.")
    settings = settings or Settings.from_env()
    service = service or ModerationService.from_settings(settings)

    app = web.Application()
    app["settings"] = settings
    app["service"] = service
    app.add_routes(
        [
            web.get("/health", health),
            web.get("/audit", audit),
            web.post("/moderate/text", moderate_text),
            web.post("/moderate/image", moderate_image),
        ]
    )
    app.on_startup.append(_startup)
    return app


async def _startup(app: "web.Application") -> None:
    await app["service"].initialize()


async def health(request: "web.Request") -> "web.Response":
    service: ModerationService = request.app["service"]
    classifier = service.image_classifier
    return web.json_response(
        {
            "status": "ok",
            "model_loaded": classifier.model_loaded,
            "model_error": classifier.load_error,
            "threshold": service.threshold,
        }
    )


async def audit(request: "web.Request") -> "web.Response":
    settings: Settings = request.app["settings"]
    service: ModerationService = request.app["service"]
    limit = _positive_int(request.query.get("limit"), settings.audit_fetch_limit)
    rows = await service.audit_log.list_recent(limit)
    return web.json_response({"events": [row.to_dict() for row in rows]})


async def moderate_text(request: "web.Request") -> "web.Response":
    payload = await _json_payload(request)
    content = str(payload.get("content") or "")
    context = ModerationContext.from_mapping(payload.get("context"))
    service: ModerationService = request.app["service"]
    decision = await service.moderate_text(content, context=context)
    return web.json_response(decision.to_dict())


async def moderate_image(request: "web.Request") -> "web.Response":
    payload = await _json_payload(request)
    raw_base64 = payload.get("image_base64")
    if not isinstance(raw_base64, str) or not raw_base64:
        raise web.HTTPBadRequest(text="image_base64 is required")
    try:
        image_bytes = base64.b64decode(raw_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise web.HTTPBadRequest(text=f"invalid base64 image: {exc}")
    filename = str(payload.get("filename") or "attachment")
    context = ModerationContext.from_mapping(payload.get("context"))
    service: ModerationService = request.app["service"]
    decision = await service.moderate_image(
        image_bytes, filename=filename, context=context
    )
    return web.json_response(decision.to_dict())


async def _json_payload(request: "web.Request") -> Dict[str, Any]:
    try:
        payload = await request.json()
    except Exception as exc:
        raise web.HTTPBadRequest(text=f"invalid JSON payload: {exc}")
    if not isinstance(payload, dict):
        raise web.HTTPBadRequest(text="JSON body must be an object")
    return payload


def _positive_int(raw: str, default: int) -> int:
    try:
        value = int(raw) if raw else default
    except ValueError:
        return default
    return max(1, value)


def main() -> None:
    if web is None:
        raise SystemExit("aiohttp is not installed. Run: python3 -m pip install -r requirements.txt")
    settings = Settings.from_env()
    app = create_app(settings=settings)
    web.run_app(app, host=settings.api_host, port=settings.api_port)


if __name__ == "__main__":
    main()

