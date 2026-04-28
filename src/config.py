"""Runtime configuration for the moderation bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import unquote, urlparse


MODERATION_MODES = ("log_only", "review", "enforce")
DEFAULT_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


def _load_dotenv_if_available() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv()


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _optional_int_env(name: str) -> Optional[int]:
    raw = os.getenv(name)
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _choice_env(name: str, default: str, choices: Iterable[str]) -> str:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    normalized = raw.strip().lower()
    return normalized if normalized in choices else default


def _id_tuple_env(name: str) -> Tuple[int, ...]:
    raw = os.getenv(name)
    if raw in (None, ""):
        return ()
    ids = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            continue
    return tuple(ids)


@dataclass(frozen=True)
class Settings:
    """Application settings loaded from environment variables."""

    discord_token: Optional[str] = None
    database_url: str = "sqlite:///moderation.db"
    nsfw_model_path: Optional[str] = None
    moderation_threshold: float = 0.75
    max_concurrent_tasks: int = 8
    min_api_interval_seconds: float = 0.05
    api_host: str = "127.0.0.1"
    api_port: int = 8080
    audit_fetch_limit: int = 25
    moderation_mode: str = "review"
    mod_log_channel_id: Optional[int] = None
    allowed_guild_ids: Tuple[int, ...] = ()
    max_attachment_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES
    enable_image_enforcement: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv_if_available()
        return cls(
            discord_token=os.getenv("DISCORD_TOKEN") or None,
            database_url=os.getenv("DATABASE_URL", "sqlite:///moderation.db"),
            nsfw_model_path=os.getenv("NSFW_MODEL_PATH") or None,
            moderation_threshold=_float_env("MODERATION_THRESHOLD", 0.75),
            max_concurrent_tasks=max(1, _int_env("MAX_CONCURRENT_TASKS", 8)),
            min_api_interval_seconds=max(
                0.0, _float_env("MIN_API_INTERVAL_SECONDS", 0.05)
            ),
            api_host=os.getenv("API_HOST", "127.0.0.1"),
            api_port=_int_env("API_PORT", 8080),
            audit_fetch_limit=max(1, _int_env("AUDIT_FETCH_LIMIT", 25)),
            moderation_mode=_choice_env("MODERATION_MODE", "review", MODERATION_MODES),
            mod_log_channel_id=_optional_int_env("MOD_LOG_CHANNEL_ID"),
            allowed_guild_ids=_id_tuple_env("ALLOWED_GUILD_IDS"),
            max_attachment_bytes=max(
                1, _int_env("MAX_ATTACHMENT_BYTES", DEFAULT_MAX_ATTACHMENT_BYTES)
            ),
            enable_image_enforcement=_bool_env("ENABLE_IMAGE_ENFORCEMENT", False),
        )

    @property
    def token_configured(self) -> bool:
        return bool(self.discord_token)

    def is_guild_allowed(self, guild_id: Optional[int]) -> bool:
        if not self.allowed_guild_ids:
            return True
        if guild_id is None:
            return False
        try:
            normalized_guild_id = int(guild_id)
        except (TypeError, ValueError):
            return False
        return normalized_guild_id in self.allowed_guild_ids

    @property
    def database_path(self) -> str:
        """Return the local SQLite path represented by DATABASE_URL."""

        if self.database_url == ":memory:":
            return self.database_url
        parsed = urlparse(self.database_url)
        if parsed.scheme in ("", "file"):
            return unquote(parsed.path or self.database_url)
        if parsed.scheme != "sqlite":
            raise ValueError("Only sqlite:/// DATABASE_URL values are supported.")
        if parsed.netloc and parsed.netloc != "":
            return unquote(f"/{parsed.netloc}{parsed.path}")
        path = unquote(parsed.path)
        if path.startswith("//"):
            path = path[1:]
        elif path.startswith("/"):
            path = path[1:]
        return str(Path(path or "moderation.db"))
