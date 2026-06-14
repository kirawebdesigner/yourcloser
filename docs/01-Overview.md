# YourCloser Overview

YourCloser is a Telegram-native commerce system for boutique stores. It is not just a chat bot; it is a multi-tenant sales workflow that lets one bot serve many shops with separate catalogs, branding, orders, and admin permissions.

## What It Does

- Shows products inside Telegram
- Lets customers browse categories, search, add to cart, and checkout
- Notifies the owner when an order is ready
- Lets the owner confirm, reject, mark on way, or mark delivered
- Supports multiple shops with isolated `shop_id` boundaries
- Supports Telegram-based shop creation and admin shop switching

## Core Principle

The bot never guesses about stock or pricing. Database values are the source of truth.

## Main Files

- `main.py` starts FastAPI and the Telegram bot
- `handlers.py` contains the customer, owner, admin, and shop-setup flows
- `db.py` contains all Supabase queries and mutations
- `tenant_context.py` resolves the current customer shop context
- `schema.sql` and the migration files define the database structure

## Read This First

The important separation is:

- Customer tenant context
- Admin operational context

That separation is what makes the system safe to scale.
