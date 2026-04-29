# AI Discord Moderation Bot

![Python](https://img.shields.io/badge/Python-3.9%2B-blue)
![Discord.py](https://img.shields.io/badge/Discord.py-2.x-5865F2)
![Tests](https://img.shields.io/badge/Tests-pytest-green)
![Mode](https://img.shields.io/badge/Default-review%20mode-orange)
![Secrets](https://img.shields.io/badge/Secrets-.env%20ignored-red)

Portfolio-ready Discord moderation bot with async message handling, review-first alerts, PyTorch-ready image screening, and SQLite audit logs.

```text
Discord Server
    |
    v
discord.py event listener
    |
    v
ModerationService ----> Text rules
    |                  Image classifier hook
    v
SQLite audit log ----> Private moderator alerts
```

## What This Does

- Watches Discord messages and image attachments in real time.
- Scores text using fast local moderation rules.
- Supports a PyTorch image-classifier hook without requiring model weights.
- Records moderation decisions in SQLite.
- Sends moderator alerts in `review` mode without deleting messages.
- Keeps raw message text, image bytes, tokens, and private IDs out of the repo.

## Safe Demo

Run everything locally without Discord credentials:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
python3 -m src.demo
python3 -m pytest
```

Expected demo behavior:

| Scenario | Result |
| --- | --- |
| Normal message | Allowed |
| Spam/scam text | Flagged or marked for delete |
| Demo-safe image marker | Allowed |
| Demo-NSFW image marker | Marked for review/delete |

## Run Live

Use this checklist when connecting the bot to your own Discord server:

- [ ] Create a Discord bot application.
- [ ] Enable Message Content Intent for that bot.
- [ ] Invite the bot with View Channels, Send Messages, Read Message History, Manage Messages, and Add Reactions.
- [ ] Copy `.env.example` to `.env`.
- [ ] Put all private values only in `.env`.
- [ ] Create a private moderator log channel.
- [ ] Start with `MODERATION_MODE=review`.
- [ ] Run the setup checker.
- [ ] Start the bot.

```bash
python3 -m src.check_setup
python3 -m src.bot
```

In Discord:

```text
!ping
!status
!audit
```

## Moderation Modes

| Mode | What happens |
| --- | --- |
| `log_only` | Audit events are recorded only. |
| `review` | Suspicious messages stay visible and private moderator alerts are sent. |
| `enforce` | High-confidence text violations can be deleted and reported. |

Image deletion remains disabled unless a real model is loaded and image enforcement is explicitly enabled.

Messages inside the configured moderator log channel are ignored, so alerts do not create alert loops or clutter the audit log.

## Privacy And Security

- Never commit `.env`.
- Never put real tokens, server IDs, channel IDs, screenshots with private data, or message contents in GitHub.
- Keep private values in your local `.env` only.
- `.env.example` contains placeholders only.
- Audit logs store metadata and decisions, not raw message text or image bytes.
- Moderator alerts include IDs and reasons, not the original message body.
- `python3 -m src.check_setup` reports whether config exists without printing secret values.

## GitHub Safety Checklist

Before pushing:

```bash
git status --short
git diff --cached --name-only
git check-ignore -v .env .venv/pyvenv.cfg moderation.db demo_moderation.db .pytest_cache/README.md
```

These must never be committed:

- `.env`
- `.venv/`
- `*.db`
- `.pytest_cache/`
- `model_weights/`
- Any file containing real tokens or private IDs

## Configuration Reference

Use `.env.example` as the template. Do not put real values in this README.

| Setting | Purpose |
| --- | --- |
| `DISCORD_TOKEN` | Local Discord bot token. Keep private. |
| `DATABASE_URL` | Local SQLite audit database location. |
| `NSFW_MODEL_PATH` | Optional local PyTorch model path. |
| `MODERATION_THRESHOLD` | Score needed for high-confidence moderation. |
| `MODERATION_MODE` | `log_only`, `review`, or `enforce`. |
| `MOD_LOG_CHANNEL_ID` | Private moderator alert channel. Keep local. |
| `ALLOWED_GUILD_IDS` | Optional server allowlist. Keep local. |
| `MAX_ATTACHMENT_BYTES` | Maximum image size the bot reads. |
| `ENABLE_IMAGE_ENFORCEMENT` | Enables image deletion only with a real loaded model. |
| `MAX_CONCURRENT_TASKS` | Concurrent moderation tasks allowed. |
| `MIN_API_INTERVAL_SECONDS` | Minimum gap between moderation task starts. |

## Project Map

```text
src/
  bot.py              live Discord bot
  check_setup.py      local setup validator
  config.py           environment settings
  moderation.py       text/image moderation orchestration
  image_classifier.py PyTorch-ready image classifier
  audit.py            SQLite audit repository
  demo.py             offline demo runner
  rate_limiter.py     async concurrency controls
  text_moderator.py   local text scoring rules
tests/
  test_*.py           unit, async, demo, and safety tests
```
