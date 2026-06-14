# Database And Migrations

YourCloser uses Supabase Postgres as the source of truth.

## Base Tables

- `products`
- `stock`
- `orders`
- `shops`
- `shop_admins`

## Migration Order

Run the SQL files in this order:

1. `schema.sql`
2. `database_fix.sql`
3. `migration_v6.sql`
4. `migration_v7.sql`

## What Each One Adds

- `schema.sql` creates the core commerce tables and seed products
- `database_fix.sql` adds `on_way` and protects order history when products are deleted
- `migration_v6.sql` adds boutique branding through `shops`
- `migration_v7.sql` adds shop ownership and admin membership through `shop_admins`

## Data Rules

- `shop_id` separates tenants
- `is_active = false` should be used for soft deleting products
- stock is decremented atomically through RPC
- orders keep a denormalized `product_name` snapshot for history

## Important Note

The bot expects the schema to exist before startup. Missing tables or missing enums will fail during runtime.
