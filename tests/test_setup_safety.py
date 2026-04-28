from src.check_setup import build_setup_report
from src.config import Settings


def test_setup_report_never_prints_token_value():
    token = "SECRET_TOKEN_VALUE.with.parts"
    report = build_setup_report(
        settings=Settings(discord_token=token, moderation_mode="review"),
        raw_env={"DISCORD_TOKEN": token, "MODERATION_MODE": "review"},
    )

    rendered = "\n".join(report.lines())
    assert token not in rendered
    assert "DISCORD_TOKEN" in rendered
    assert "configured" in rendered


def test_setup_report_warns_about_invalid_mode_without_secret_leak():
    token = "SECRET_TOKEN_VALUE.with.parts"
    report = build_setup_report(
        settings=Settings(discord_token=token, moderation_mode="review"),
        raw_env={"DISCORD_TOKEN": token, "MODERATION_MODE": "bad-mode"},
    )

    rendered = "\n".join(report.lines())
    assert token not in rendered
    assert "invalid value ignored" in rendered

