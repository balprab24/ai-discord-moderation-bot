# AI Discord Moderation Bot

An event-driven Discord moderation bot built with Python, `discord.py`, PyTorch-ready image classification, async rate limiting, and SQLite audit logs.

This repo is set up for two uses:

- Show the project safely with an offline demo.
- Run the bot in a real Discord server using local environment variables.

No real tokens, server IDs, channel IDs, message contents, or private values belong in this README.

## Start Here

Use this like a checklist.

- [ ] Create a virtual environment.
- [ ] Install dependencies.
- [ ] Run the offline demo.
- [ ] Run the setup checker.
- [ ] Configure your local `.env` file.
- [ ] Invite the bot to your Discord server.
- [ ] Start in `review` mode.
- [ ] Watch moderator alerts before enabling enforcement.

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-dev.txt
```

Run the offline demo:

```bash
python3 -m src.demo
```

Run the setup checker:

```bash
python3 -m src.check_setup
```

Run tests:

```bash
python3 -m pytest
```

## Live Discord Checklist

- [ ] Create a Discord application and bot in the Discord Developer Portal.
- [ ] Enable the Message Content Intent for the bot.
- [ ] Invite the bot with these permissions:
  - View Channels
  - Send Messages
  - Read Message History
  - Manage Messages
  - Add Reactions
- [ ] Copy `.env.example` to `.env`.
- [ ] Put your real bot token only in `.env`.
- [ ] Create a private moderator log channel.
- [ ] Put the moderator channel ID only in `.env`.
- [ ] Optionally restrict the bot to your server ID in `.env`.
- [ ] Run the setup checker again.
- [ ] Start the bot.

```bash
python3 -m src.bot
```

## First Run Mode

Start with:

```text
MODERATION_MODE=review
```

In `review` mode, the bot keeps suspicious messages visible and sends moderator alerts. This lets you tune rules before allowing message deletion.

Available modes:

| Mode       | Behavior                                                        |
| ---------- | --------------------------------------------------------------- |
| `log_only` | Records audit events only. No alerts or message actions.        |
| `review`   | Sends moderator alerts. Does not delete messages.               |
| `enforce`  | Deletes high-confidence text violations and reports the action. |

Image enforcement stays disabled unless a real model is configured and image enforcement is explicitly enabled.

## Bot Commands

Use these in Discord after the bot is running:

| Command   | Who should use it | What it does                                                 |
| --------- | ----------------- | ------------------------------------------------------------ |
| `!ping`   | Anyone            | Confirms the bot is online.                                  |
| `!status` | Moderators        | Shows safe runtime status without secrets.                   |
| `!audit`  | Moderators        | Shows recent moderation actions without raw message content. |

## Privacy Rules

- Never commit `.env`.
- Never paste your bot token into code, docs, screenshots, issues, commits, or chat.
- Never put real server IDs or private channel IDs in this README.
- Keep private values in your local `.env` only.
- Audit logs store IDs, action, score, reason, and timestamps.
- Audit logs do not store raw message text or image bytes.
- Moderator alerts do not repeat the original message content.
- `python3 -m src.check_setup` reports whether secret values are configured without printing them.

## Safe Configuration Reference

Use `.env.example` as the template. The values below describe what each setting does; they are not real private values.

| Setting                    | Purpose                                               |
| -------------------------- | ----------------------------------------------------- |
| `DISCORD_TOKEN`            | Your local bot token. Keep it private.                |
| `DATABASE_URL`             | Local SQLite audit database location.                 |
| `NSFW_MODEL_PATH`          | Optional local PyTorch model path.                    |
| `MODERATION_THRESHOLD`     | Score needed for a high-confidence decision.          |
| `MODERATION_MODE`          | `log_only`, `review`, or `enforce`.                   |
| `MOD_LOG_CHANNEL_ID`       | Private moderator alert channel. Keep it local.       |
| `ALLOWED_GUILD_IDS`        | Optional server allowlist. Keep it local.             |
| `MAX_ATTACHMENT_BYTES`     | Maximum image size the bot will read.                 |
| `ENABLE_IMAGE_ENFORCEMENT` | Enables image deletion only with a real loaded model. |
| `MAX_CONCURRENT_TASKS`     | Concurrent moderation tasks allowed.                  |
| `MIN_API_INTERVAL_SECONDS` | Minimum gap between moderation task starts.           |

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
