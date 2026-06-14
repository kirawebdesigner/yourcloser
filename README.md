# YourCloser

Production-ready Telegram sales assistant for boutique shops.

YourCloser lets customers browse products, choose sizes or variants, place orders, and receive order status updates directly inside Telegram. Shop owners manage products, stock, admins, broadcasts, and order actions from the bot admin panel.

## Current Status

- Customer storefront: browse, search, cart, buy now, checkout, and order tracking.
- Admin panel: shop switching, add products, product catalog, stock/price editing, recent orders, broadcasts, admin management, and plan limit enforcement.
- Multi-shop ready: every database call is scoped by `shop_id`.
- Stock-safe checkout: final checkout uses atomic stock decrement.
- Production checks: `chaos_test.py` validates callback routing, tenant isolation, checkout locks, admin recovery, and plan gates.

Latest validation result:

```text
88/88 tests passed
```

## Tech Stack

| Layer | Tech |
| --- | --- |
| Bot | python-telegram-bot v21 |
| API | FastAPI + Uvicorn |
| Database | Supabase Postgres |
| Deployment | Choreo compatible Docker service |

## Important Files

| File | Purpose |
| --- | --- |
| `main.py` | FastAPI app, webhook entrypoint, polling mode for local dev |
| `handlers.py` | Telegram customer, checkout, owner, and admin flows |
| `db.py` | Supabase queries and tenant-safe DB helpers |
| `plans.py` | Starter, Growth, Pro, and Custom plan definitions |
| `tenant_context.py` | Resolves active `shop_id` from deep links/session |
| `chaos_test.py` | Production validation suite |
| `schema.sql` | Base Supabase schema and demo catalog |
| `migration_v4.sql` to `migration_v10.sql` | Required production migrations |
| `.choreo/component.yaml` | Choreo REST endpoint configuration |

## Environment Variables

Set these in `.env` for local development and in Choreo environment variables for production:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_OWNER_CHAT_ID=your_telegram_user_id
SUPABASE_URL=your_supabase_project_url
SUPABASE_SERVICE_KEY=your_supabase_service_role_key
WEBHOOK_URL=https://your-public-choreo-url
```

Notes:

- `TELEGRAM_BOT_TOKEN` comes from `@BotFather`.
- `TELEGRAM_OWNER_CHAT_ID` comes from `@userinfobot`.
- `SUPABASE_SERVICE_KEY` must be the service role key, not the anon key.
- Keep `.env` private. It is ignored by Git.
- For local polling mode, leave `WEBHOOK_URL` empty.

## Supabase Setup

Run these files in the Supabase SQL Editor in this order:

```text
schema.sql
migration_v4.sql
migration_v5.sql
migration_v6.sql
migration_v7.sql
migration_v8.sql
migration_v9.sql
migration_v10.sql
```

If you also keep `database_fix.sql` from the parent workspace, run it after `migration_v10.sql`.

The current production-ready database state should keep:

- One default test shop: `default`
- Demo products under `default`
- No test orders
- The owner assigned in `shop_admins`

## Local Development

```powershell
cd C:\Users\kirub\OneDrive\Desktop\Me\EthioCloser\bot
pip install -r requirements.txt
python main.py
```

Local mode uses Telegram polling when `WEBHOOK_URL` is empty.

Run validation:

```powershell
python -m py_compile main.py handlers.py db.py config.py tenant_context.py chaos_test.py
python chaos_test.py
```

## Choreo Deployment

This repo is ready for Choreo deployment from the `main` branch.

1. Push changes to GitHub.
2. In Choreo, connect the GitHub repo and select this service.
3. Confirm the endpoint uses port `8000`.
4. Add the environment variables listed above.
5. Deploy the latest commit.
6. Set `WEBHOOK_URL` to the public Choreo service URL.
7. Redeploy after setting `WEBHOOK_URL` so the bot registers the Telegram webhook.

Health endpoints:

```text
GET /
GET /health
POST /webhook
```

## Client Onboarding

To add a first real client:

1. Collect shop name, selected plan, owner Telegram user ID, support link, delivery text, welcome text, shop emoji, and product list.
2. In Telegram, run `/create_shop`.
3. Create the boutique, choose the plan, add the client owner Telegram ID, and save the generated `shop_id`.
4. Run `/admin`.
5. Select the new shop.
6. Add products with photos, sizes/variants, prices, and quantities.
7. Place one test order before giving the shop link to the client.

Customer link format:

```text
https://t.me/YOUR_BOT_USERNAME?start=SHOP_ID
```

## Manual Button Checklist

Before pitching a client, manually test:

Customer:

- `/start`
- Trending Now
- Best Sellers
- New Drops
- Under 5,000 ETB
- Category buttons
- Search
- Product navigation
- Add to Cart
- Buy Now
- Checkout
- Cancel order
- Track Orders

Admin:

- `/admin`
- Switch Shop
- Add Product
- Publish Product
- My Products
- Toggle Status
- Edit Name
- Manage Stock
- Edit Price
- Edit Quantity
- Recent Orders
- Broadcast
- Manage Admins
- Revoke Admin

Plan enforcement:

- Starter blocks the 31st active product, additional admin seats, and broadcasts.
- Growth blocks the 151st active product and additional admin seats, but allows broadcasts.
- Pro allows multiple admins, broadcasts, and reporting-oriented admin views.
- Custom is controlled through `shops.custom_limits`.

Owner order controls:

- Confirm
- Reject
- Mark On Way
- Mark Delivered

## Reliability Rules

- The bot never guesses stock or price.
- Every product/order/admin query is scoped to `shop_id`.
- Checkout rechecks stock before order creation.
- Multi-item checkout is atomic at the database level: either every order line and stock decrement succeeds, or none do.
- Stale checkout/admin/order buttons are guarded so they cannot trigger the wrong action.
- Owners/admins receive order controls directly in Telegram.
