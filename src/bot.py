"""Discord.py entrypoint for live server moderation."""

from __future__ import annotations

import logging
from typing import Iterable

from .config import Settings
from .models import ALLOW, AuditEvent, DELETE, FLAG, ModerationContext, ModerationDecision
from .moderation import ModerationService

try:
    import discord
    from discord.ext import commands
except ImportError:  # pragma: no cover - depends on optional dependency
    discord = None
    commands = None

DiscordForbidden = discord.Forbidden if discord is not None else PermissionError
DiscordHTTPException = discord.HTTPException if discord is not None else Exception


IMAGE_PREFIXES = ("image/",)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp")
LIVE_REPORT = "report"
LIVE_ACTIONS = (ALLOW, LIVE_REPORT, FLAG, DELETE)

logger = logging.getLogger(__name__)


def create_bot(
    settings: Settings = None, service: ModerationService = None
) -> "commands.Bot":
    if discord is None or commands is None:
        raise RuntimeError("discord.py is required for the live bot. Install requirements.txt.")
    settings = settings or Settings.from_env()
    service = service or ModerationService.from_settings(settings)

    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    bot.moderation_service = service  # type: ignore[attr-defined]

    @bot.event
    async def on_ready() -> None:
        await service.initialize()
        logger.info("Logged in as %s. Monitoring %s server(s).", bot.user, len(bot.guilds))
        await _log_startup_permissions(bot, settings)

    @bot.event
    async def on_message(message: "discord.Message") -> None:
        if message.author.bot:
            return
        if not settings.is_guild_allowed(_guild_id(message)):
            logger.info("Ignoring message from unallowed guild_id=%s", _guild_id(message))
            return

        context = ModerationContext.from_discord_message(message)
        if message.content:
            decision = await service.moderate_text(message.content, context=context)
            live_action = live_action_for_decision(
                decision,
                settings=settings,
                image_model_loaded=service.image_classifier.model_loaded,
            )
            await _apply_live_action(bot, message, decision, live_action, settings)
            if live_action == DELETE:
                return

        for attachment in _image_attachments(message.attachments):
            image_context = ModerationContext(
                message_id=f"{message.id}:{attachment.id}",
                guild_id=context.guild_id,
                channel_id=context.channel_id,
                user_id=context.user_id,
            )
            if is_attachment_too_large(attachment, settings):
                decision = oversized_attachment_decision(
                    image_context,
                    filename=attachment.filename,
                    size_bytes=getattr(attachment, "size", 0) or 0,
                    max_bytes=settings.max_attachment_bytes,
                )
                await service.audit_log.record(AuditEvent.from_decision(decision, image_context))
                await _apply_live_action(bot, message, decision, LIVE_REPORT, settings)
                continue

            try:
                image_bytes = await attachment.read()
            except DiscordHTTPException as exc:
                logger.warning(
                    "Could not read attachment for message_id=%s: %s",
                    message.id,
                    exc,
                )
                continue
            decision = await service.moderate_image(
                image_bytes,
                filename=attachment.filename,
                context=image_context,
            )
            live_action = live_action_for_decision(
                decision,
                settings=settings,
                image_model_loaded=service.image_classifier.model_loaded,
            )
            await _apply_live_action(bot, message, decision, live_action, settings)
            if live_action == DELETE:
                return

        await bot.process_commands(message)

    @bot.command(name="ping")
    async def ping_command(ctx: "commands.Context") -> None:
        await ctx.reply("Pong. Moderation bot is running.", mention_author=False)

    @bot.command(name="status")
    @commands.has_permissions(manage_messages=True)
    async def status_command(ctx: "commands.Context") -> None:
        model_loaded = service.image_classifier.model_loaded
        image_enforcement = settings.enable_image_enforcement and model_loaded
        lines = [
            f"mode={settings.moderation_mode}",
            f"database={safe_database_label(settings.database_path)}",
            f"model_loaded={model_loaded}",
            f"image_enforcement={image_enforcement}",
            f"mod_channel_configured={settings.mod_log_channel_id is not None}",
            f"allowed_guilds={len(settings.allowed_guild_ids) or 'any'}",
        ]
        await ctx.reply("\n".join(lines), mention_author=False)

    @bot.command(name="audit")
    @commands.has_permissions(manage_messages=True)
    async def audit_command(ctx: "commands.Context", limit: int = 5) -> None:
        rows = await service.audit_log.list_recent(max(1, min(limit, 10)))
        if not rows:
            await ctx.reply("No moderation actions recorded yet.", mention_author=False)
            return
        lines = [
            f"#{row.id} {row.created_at} {row.action.upper()} {row.content_type} "
            f"score={row.confidence:.2f} category={row.category} "
            f"msg={row.message_id} user={row.user_id or 'unknown'} reason={row.reason}"
            for row in rows
        ]
        await ctx.reply("\n".join(lines), mention_author=False)

    return bot


def live_action_for_decision(
    decision: ModerationDecision,
    settings: Settings,
    image_model_loaded: bool = False,
) -> str:
    """Convert a raw moderation decision into a safe live-server action."""

    if decision.action == ALLOW:
        return ALLOW
    if settings.moderation_mode == "log_only":
        return ALLOW
    if settings.moderation_mode == "review":
        return LIVE_REPORT
    if decision.content_type == "image" and not (
        settings.enable_image_enforcement and image_model_loaded
    ):
        return LIVE_REPORT
    if decision.action == DELETE:
        return DELETE
    if decision.action == FLAG:
        return FLAG
    return ALLOW


async def _apply_live_action(
    bot: "commands.Bot",
    message: "discord.Message",
    decision: ModerationDecision,
    live_action: str,
    settings: Settings,
) -> None:
    if live_action not in LIVE_ACTIONS:
        raise ValueError(f"unknown live action: {live_action}")

    if live_action == ALLOW:
        return

    if live_action == DELETE:
        try:
            await message.delete()
        except DiscordForbidden:
            logger.warning("Missing permission to delete message_id=%s", decision.message_id)
        except DiscordHTTPException as exc:
            logger.warning("Could not delete message_id=%s: %s", decision.message_id, exc)
    elif live_action == FLAG:
        try:
            await message.add_reaction("\N{WARNING SIGN}\ufe0f")
        except DiscordHTTPException:
            logger.warning("Could not add warning reaction to message_id=%s", decision.message_id)

    await _send_mod_alert(bot, message, decision, live_action, settings)


async def _send_mod_alert(
    bot: "commands.Bot",
    message: "discord.Message",
    decision: ModerationDecision,
    live_action: str,
    settings: Settings,
) -> None:
    if settings.mod_log_channel_id is None:
        logger.info(
            "Moderation %s for message_id=%s action=%s score=%.2f reason=%s",
            live_action,
            decision.message_id,
            decision.action,
            decision.confidence,
            decision.reason,
        )
        return

    channel = bot.get_channel(settings.mod_log_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(settings.mod_log_channel_id)
        except DiscordHTTPException as exc:
            logger.warning(
                "Could not fetch MOD_LOG_CHANNEL_ID=%s: %s",
                settings.mod_log_channel_id,
                exc,
            )
            return

    alert = format_moderator_alert(message, decision, live_action)
    send_kwargs = {}
    if discord is not None:
        send_kwargs["allowed_mentions"] = discord.AllowedMentions.none()
    try:
        await channel.send(alert, **send_kwargs)
    except TypeError:
        await channel.send(alert)
    except DiscordHTTPException as exc:
        logger.warning(
            "Could not send moderation alert for message_id=%s: %s",
            decision.message_id,
            exc,
        )


def format_moderator_alert(
    message: "discord.Message", decision: ModerationDecision, live_action: str
) -> str:
    jump_url = getattr(message, "jump_url", None)
    guild_id = _guild_id(message) or "unknown"
    channel_id = getattr(getattr(message, "channel", None), "id", "unknown")
    author_id = getattr(getattr(message, "author", None), "id", "unknown")
    lines = [
        "Moderation alert",
        f"live_action={live_action}",
        f"decision={decision.action}",
        f"type={decision.content_type}",
        f"score={decision.confidence:.2f}",
        f"category={decision.category}",
        f"reason={decision.reason}",
        f"guild_id={guild_id}",
        f"channel_id={channel_id}",
        f"user_id={author_id}",
        f"message_id={decision.message_id}",
    ]
    if jump_url:
        lines.append(f"message_link={jump_url}")
    return "\n".join(lines)


def oversized_attachment_decision(
    context: ModerationContext,
    filename: str,
    size_bytes: int,
    max_bytes: int,
) -> ModerationDecision:
    return ModerationDecision(
        message_id=context.message_id,
        content_type="image",
        action=FLAG,
        confidence=0.5,
        reason=(
            f"attachment {safe_filename(filename)} is {size_bytes} bytes; "
            f"limit is {max_bytes} bytes"
        ),
        latency_ms=0.0,
        category="attachment_limit",
        source="attachment_guardrail",
    )


def is_attachment_too_large(attachment: object, settings: Settings) -> bool:
    size = getattr(attachment, "size", None)
    if size is None:
        return False
    try:
        size_bytes = int(size)
    except (TypeError, ValueError):
        return False
    return size_bytes > settings.max_attachment_bytes


def _image_attachments(attachments: Iterable["discord.Attachment"]):
    for attachment in attachments:
        content_type = (attachment.content_type or "").lower()
        filename = (attachment.filename or "").lower()
        if content_type.startswith(IMAGE_PREFIXES) or filename.endswith(IMAGE_SUFFIXES):
            yield attachment


async def _log_startup_permissions(bot: "commands.Bot", settings: Settings) -> None:
    for guild in bot.guilds:
        guild_id = getattr(guild, "id", None)
        if not settings.is_guild_allowed(guild_id):
            continue
        me = getattr(guild, "me", None)
        permissions = getattr(me, "guild_permissions", None)
        missing = missing_permissions(permissions)
        if missing:
            logger.warning("Guild id=%s is missing permissions: %s", guild_id, ", ".join(missing))

    if settings.mod_log_channel_id is None:
        logger.warning("MOD_LOG_CHANNEL_ID is not set; moderator alerts will use local logs")
        return

    channel = bot.get_channel(settings.mod_log_channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(settings.mod_log_channel_id)
        except DiscordHTTPException as exc:
            logger.warning("Could not verify mod log channel: %s", exc)
            return
    guild = getattr(channel, "guild", None)
    me = getattr(guild, "me", None)
    if guild is not None and hasattr(channel, "permissions_for") and me is not None:
        missing = missing_permissions(channel.permissions_for(me), require_manage_messages=False)
        if missing:
            logger.warning(
                "Mod log channel id=%s is missing permissions: %s",
                settings.mod_log_channel_id,
                ", ".join(missing),
            )


def missing_permissions(permissions: object, require_manage_messages: bool = True):
    if permissions is None:
        return ["view_channel", "send_messages", "read_message_history"]
    required = ["view_channel", "send_messages", "read_message_history", "add_reactions"]
    if require_manage_messages:
        required.append("manage_messages")
    return [name for name in required if not bool(getattr(permissions, name, False))]


def safe_database_label(database_path: str) -> str:
    path = str(database_path)
    if path.startswith("/") and "/" in path.strip("/"):
        return f"<local>/{path.rsplit('/', 1)[-1]}"
    return path


def safe_filename(filename: str) -> str:
    return (filename or "attachment").replace("\n", "_").replace("\r", "_")[:80]


def _guild_id(message: "discord.Message"):
    guild = getattr(message, "guild", None)
    guild_id = getattr(guild, "id", None)
    if guild_id is None:
        return None
    try:
        return int(guild_id)
    except (TypeError, ValueError):
        return None


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings.from_env()
    if not settings.discord_token:
        raise SystemExit("DISCORD_TOKEN is required for the live bot. Copy .env.example to .env.")
    bot = create_bot(settings=settings)
    bot.run(settings.discord_token)


if __name__ == "__main__":
    main()
