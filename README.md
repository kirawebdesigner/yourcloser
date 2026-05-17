# YourCloser 🤖

**The Automated Sales System for Telegram Boutiques**

A 24/7 Telegram sales assistant that handles product inquiries, checks real stock, captures orders, and notifies shop owners — so they never miss a sale while sleeping.

## Architecture

```
Customer (Telegram) → Bot Handlers → Supabase DB
                                   ↓
                          Owner Notification (Telegram)
```

### Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI server + entry point (webhook & polling modes) |
| `handlers.py` | Telegram conversation flow (7-step sales funnel) |
| `db.py` | All Supabase queries (zero guessing policy) |
| `config.py` | Environment variable loader |
| `schema.sql` | Database schema + demo data |

## Setup

### 1. Create Telegram Bot

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the bot token

### 2. Get Your Telegram User ID

1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy your user ID (this is where order notifications go)

### 3. Setup Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. Go to SQL Editor → paste `schema.sql` → Run
3. Copy your project URL and service role key from Settings → API

### 4. Configure Environment

```bash
cd bot
copy .env.example .env
# Edit .env with your actual values
```

### 5. Install & Run

```bash
pip install -r requirements.txt

# Local dev (polling mode — no domain needed):
python main.py

# Production (webhook mode — needs public URL):
# Set WEBHOOK_URL in .env first
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Sales Flow

```
/start → "What product?" → Search results
  → Select product → Available sizes shown
  → Select size → Price displayed, ask name
  → Enter name → Ask phone
  → Enter phone → Ask location
  → Enter location → Order summary + confirm
  → Confirm → Order saved → Owner notified
```

## Reliability Rules

1. **Bot never guesses stock** — only reports what the DB returns
2. **Triple stock verification** — checked at search, selection, AND confirmation
3. **Owner has final word** — confirm/reject buttons on every order notification
4. **Ethiopian phone validation** — 09xx/07xx/+251xx format enforced

## Production Deployment

For production, you need a public HTTPS URL. Options:
- **Railway.app** — easiest, free tier available
- **Render.com** — free tier with auto-sleep
- **VPS** — any Ubuntu server with nginx + certbot

Set `WEBHOOK_URL` to your public URL and the bot will auto-register the webhook on startup.

## Demo Data

The schema includes a fake sneaker store with 5 products (Nike AF1, Yeezy, Jordan 1, NB 550, Dunk Low) and realistic stock/pricing in ETB. Remove the demo data section from `schema.sql` before going live with a real client.
