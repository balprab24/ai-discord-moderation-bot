import pytest

from src.bot import (
    LIVE_REPORT,
    _apply_live_action,
    format_moderator_alert,
    is_mod_log_channel,
    is_attachment_too_large,
    live_action_for_decision,
    missing_permissions,
    oversized_attachment_decision,
    safe_database_label,
    should_ignore_message,
)
from src.config import Settings
from src.models import ALLOW, DELETE, FLAG, ModerationContext, ModerationDecision


def decision(action=DELETE, content_type="text"):
    return ModerationDecision(
        message_id="msg-123",
        content_type=content_type,
        action=action,
        confidence=0.91 if action == DELETE else 0.55,
        reason="matched moderation rule",
        latency_ms=1.2,
        category="spam",
        source="test",
    )


def test_live_action_log_only_never_mutates_or_reports():
    settings = Settings(moderation_mode="log_only")

    assert live_action_for_decision(decision(DELETE), settings) == ALLOW
    assert live_action_for_decision(decision(FLAG), settings) == ALLOW


def test_live_action_review_reports_without_deleting():
    settings = Settings(moderation_mode="review")

    assert live_action_for_decision(decision(DELETE), settings) == LIVE_REPORT
    assert live_action_for_decision(decision(FLAG), settings) == LIVE_REPORT


def test_live_action_enforce_deletes_high_confidence_text():
    settings = Settings(moderation_mode="enforce")

    assert live_action_for_decision(decision(DELETE), settings) == DELETE
    assert live_action_for_decision(decision(FLAG), settings) == FLAG


def test_live_action_image_enforcement_requires_loaded_real_model():
    image_decision = decision(DELETE, content_type="image")

    assert live_action_for_decision(
        image_decision,
        Settings(moderation_mode="enforce", enable_image_enforcement=False),
        image_model_loaded=True,
    ) == LIVE_REPORT
    assert live_action_for_decision(
        image_decision,
        Settings(moderation_mode="enforce", enable_image_enforcement=True),
        image_model_loaded=False,
    ) == LIVE_REPORT
    assert live_action_for_decision(
        image_decision,
        Settings(moderation_mode="enforce", enable_image_enforcement=True),
        image_model_loaded=True,
    ) == DELETE


def test_guild_allowlist_and_attachment_size_guardrail():
    settings = Settings(allowed_guild_ids=(111, 222), max_attachment_bytes=10)
    attachment = type("Attachment", (), {"size": 11})()

    assert settings.is_guild_allowed(111)
    assert not settings.is_guild_allowed(333)
    assert is_attachment_too_large(attachment, settings)


def test_oversized_attachment_decision_omits_raw_content():
    context = ModerationContext(message_id="msg-123:att-1")
    result = oversized_attachment_decision(
        context,
        filename="large.png",
        size_bytes=20,
        max_bytes=10,
    )

    assert result.action == FLAG
    assert result.category == "attachment_limit"
    assert "large.png" in result.reason


def test_alert_and_status_helpers_do_not_include_message_content_or_local_path():
    message = FakeMessage(content="super secret message body")
    alert = format_moderator_alert(message, decision(DELETE), LIVE_REPORT)

    assert "super secret message body" not in alert
    assert "message_id=msg-123" in alert
    assert safe_database_label("/Users/example/private/moderation.db") == "<local>/moderation.db"


def test_mod_log_channel_is_ignored_when_configured():
    settings = Settings(mod_log_channel_id=333)
    message = FakeMessage(content="free nitro giveaway winner click this link")

    assert is_mod_log_channel(message, settings)
    assert should_ignore_message(message, settings)


def test_normal_channel_is_not_ignored_when_mod_log_is_configured():
    settings = Settings(mod_log_channel_id=999)
    message = FakeMessage(content="free nitro giveaway winner click this link")

    assert not is_mod_log_channel(message, settings)
    assert not should_ignore_message(message, settings)


def test_bot_author_message_is_ignored():
    settings = Settings(mod_log_channel_id=999)
    message = FakeMessage()
    message.author.bot = True

    assert should_ignore_message(message, settings)


def test_unallowed_guild_message_is_ignored():
    settings = Settings(allowed_guild_ids=(999,))
    message = FakeMessage()

    assert should_ignore_message(message, settings)


@pytest.mark.asyncio
async def test_apply_review_action_sends_private_mod_alert_without_mutating_message():
    channel = FakeChannel()
    bot = FakeBot(channel)
    message = FakeMessage(content="do not copy this into alerts")
    settings = Settings(moderation_mode="review", mod_log_channel_id=999)

    await _apply_live_action(bot, message, decision(DELETE), LIVE_REPORT, settings)

    assert not message.deleted
    assert message.reactions == []
    assert len(channel.sent) == 1
    assert "do not copy this into alerts" not in channel.sent[0]


@pytest.mark.asyncio
async def test_apply_enforce_action_deletes_and_alerts():
    channel = FakeChannel()
    bot = FakeBot(channel)
    message = FakeMessage()
    settings = Settings(moderation_mode="enforce", mod_log_channel_id=999)

    await _apply_live_action(bot, message, decision(DELETE), DELETE, settings)

    assert message.deleted
    assert len(channel.sent) == 1


def test_missing_permissions_reports_required_capabilities():
    permissions = type(
        "Permissions",
        (),
        {
            "view_channel": True,
            "send_messages": True,
            "read_message_history": False,
            "add_reactions": True,
            "manage_messages": False,
        },
    )()

    assert missing_permissions(permissions) == ["read_message_history", "manage_messages"]


class FakeChannel:
    id = 333

    def __init__(self):
        self.sent = []

    async def send(self, content, **kwargs):
        self.sent.append(content)


class FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, channel_id):
        if channel_id == 999:
            return self.channel
        return None

    async def fetch_channel(self, channel_id):
        return self.get_channel(channel_id)


class FakeMessage:
    id = 123
    jump_url = "https://discord.com/channels/111/333/123"

    def __init__(self, content="hello"):
        self.content = content
        self.guild = type("Guild", (), {"id": 111})()
        self.channel = type("Channel", (), {"id": 333})()
        self.author = type("Author", (), {"id": 222})()
        self.deleted = False
        self.reactions = []

    async def delete(self):
        self.deleted = True

    async def add_reaction(self, reaction):
        self.reactions.append(reaction)
