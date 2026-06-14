# Deployment And Operations

This file covers how the bot is run and operated.

## Runtime Modes

- Polling mode for local development
- Webhook mode for production

## Local Run

```powershell
python main.py
```

## Production Run

Set `WEBHOOK_URL` and run through a host such as Railway, Render, Choreo, or a VPS.

## Operational Principles

- Database is the source of truth
- UI state is derived from Telegram context
- Admin actions are tied to a selected shop
- Stock mutation must be atomic

## Logging and Stability

The code should log:

- webhook failures
- callback failures
- stock conflicts
- broadcast failures
- setup failures

This is the layer that keeps the system usable after the first real clients arrive.

## Recommended Practice

- Prefer soft deletes for products
- Keep order history intact
- Avoid hardcoding secrets
- Keep staff permissions explicit
