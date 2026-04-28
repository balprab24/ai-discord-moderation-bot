"""Local setup checks that never print secrets."""

from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from typing import Iterable, List, Optional

from .config import MODERATION_MODES, Settings


@dataclass(frozen=True)
class SetupCheck:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class SetupReport:
    checks: List[SetupCheck]

    @property
    def ok(self) -> bool:
        return all(check.status != "error" for check in self.checks)

    def lines(self) -> List[str]:
        icons = {"ok": "OK", "warning": "WARN", "error": "ERROR"}
        return [
            f"[{icons.get(check.status, check.status.upper())}] "
            f"{check.name}: {check.message}"
            for check in self.checks
        ]


def build_setup_report(
    settings: Optional[Settings] = None,
    raw_env: Optional[dict] = None,
) -> SetupReport:
    settings = settings or Settings.from_env()
    if raw_env is None:
        raw_env = os.environ
    checks = [
        _dependency_check("discord.py", "discord"),
        _dependency_check("aiohttp", "aiohttp"),
        _dependency_check("torch", "torch", required=False),
        _token_check(raw_env.get("DISCORD_TOKEN")),
        _mode_check(raw_env.get("MODERATION_MODE"), settings.moderation_mode),
        _mod_channel_check(settings),
        _allowlist_check(settings.allowed_guild_ids),
        _attachment_limit_check(settings.max_attachment_bytes),
        _image_enforcement_check(settings),
    ]
    return SetupReport(checks)


def main() -> None:
    report = build_setup_report()
    print("Discord moderation bot setup check")
    print("No secret values are displayed.")
    for line in report.lines():
        print(line)
    if not report.ok:
        raise SystemExit(1)


def _dependency_check(
    display_name: str, module_name: str, required: bool = True
) -> SetupCheck:
    if importlib.util.find_spec(module_name) is not None:
        return SetupCheck(display_name, "ok", "installed")
    status = "error" if required else "warning"
    detail = "required for live bot/API use" if required else "optional unless using a real model"
    return SetupCheck(display_name, status, f"not installed; {detail}")


def _token_check(token: Optional[str]) -> SetupCheck:
    if not token:
        return SetupCheck(
            "DISCORD_TOKEN",
            "error",
            "not configured; copy .env.example to .env and paste the token there",
        )
    if token == "your_discord_bot_token_here":
        return SetupCheck("DISCORD_TOKEN", "error", "still set to the example placeholder")
    if len(token) < 40 or "." not in token:
        return SetupCheck("DISCORD_TOKEN", "warning", "configured, but format looks unusual")
    return SetupCheck("DISCORD_TOKEN", "ok", "configured")


def _mode_check(raw_mode: Optional[str], parsed_mode: str) -> SetupCheck:
    if raw_mode and raw_mode.strip().lower() not in MODERATION_MODES:
        choices = ", ".join(MODERATION_MODES)
        return SetupCheck(
            "MODERATION_MODE",
            "warning",
            f"invalid value ignored; using {parsed_mode}. Allowed: {choices}",
        )
    return SetupCheck("MODERATION_MODE", "ok", f"using {parsed_mode}")


def _mod_channel_check(settings: Settings) -> SetupCheck:
    if settings.moderation_mode == "log_only":
        return SetupCheck("MOD_LOG_CHANNEL_ID", "ok", "not required in log_only mode")
    if settings.mod_log_channel_id is None:
        return SetupCheck(
            "MOD_LOG_CHANNEL_ID",
            "warning",
            "not configured; review/enforce alerts will only be logged locally",
        )
    return SetupCheck("MOD_LOG_CHANNEL_ID", "ok", "configured")


def _allowlist_check(allowed_guild_ids: Iterable[int]) -> SetupCheck:
    ids = tuple(allowed_guild_ids)
    if not ids:
        return SetupCheck("ALLOWED_GUILD_IDS", "warning", "empty; bot will respond in any invited server")
    return SetupCheck("ALLOWED_GUILD_IDS", "ok", f"{len(ids)} server id(s) configured")


def _attachment_limit_check(max_attachment_bytes: int) -> SetupCheck:
    if max_attachment_bytes <= 0:
        return SetupCheck("MAX_ATTACHMENT_BYTES", "error", "must be greater than zero")
    size_mb = max_attachment_bytes / (1024 * 1024)
    return SetupCheck("MAX_ATTACHMENT_BYTES", "ok", f"limited to {size_mb:.1f} MB")


def _image_enforcement_check(settings: Settings) -> SetupCheck:
    if not settings.enable_image_enforcement:
        return SetupCheck("ENABLE_IMAGE_ENFORCEMENT", "ok", "disabled by default")
    if not settings.nsfw_model_path:
        return SetupCheck(
            "ENABLE_IMAGE_ENFORCEMENT",
            "warning",
            "enabled without NSFW_MODEL_PATH; bot will still avoid image deletes",
        )
    return SetupCheck("ENABLE_IMAGE_ENFORCEMENT", "ok", "enabled with a model path configured")


if __name__ == "__main__":
    main()
