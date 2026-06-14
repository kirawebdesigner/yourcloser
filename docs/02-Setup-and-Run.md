# Setup And Run

This file describes how to get the bot running locally.

## Requirements

- Python 3.11+ recommended
- Supabase project
- Telegram bot token from BotFather
- Your Telegram user ID for owner access

## Environment Variables

Set these in `bot/.env`:

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_OWNER_CHAT_ID=...
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
HOST=0.0.0.0
PORT=8000
WEBHOOK_URL=
```

Leave `WEBHOOK_URL` empty for local polling mode.

## Install

```powershell
cd C:\Users\kirub\OneDrive\Desktop\Me\EthioCloser\bot
pip install -r requirements.txt
```

## Run

```powershell
python main.py
```

If `WEBHOOK_URL` is empty, the app runs in polling mode locally.

## Verify

- `GET /` returns service health
- `GET /health` returns `healthy`
- `/start` opens the customer storefront
- `/admin` opens the owner panel
