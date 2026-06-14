# Troubleshooting And Next Steps

## Common Problems

### Bot Does Not Start

- Check `.env`
- Check that `python-telegram-bot`, `supabase`, and `python-dotenv` are installed
- Check that the Supabase schema has been applied

### `/admin` Shows No Shops

- Run `migration_v6.sql`
- Run `migration_v7.sql`
- Make sure your Telegram user is inserted into `shop_admins`

### Customer Link Opens Wrong Shop

- Check the `shop_id` in the deep link
- Confirm the product belongs to the expected shop
- Confirm the `shops` row exists

### Order Status Updates Fail

- Confirm the callback includes the correct `shop_id`
- Confirm the order belongs to that shop

## What To Build Next

1. Product editing and restocking
2. Soft delete and pause listing
3. Updated-by audit fields
4. Logging table
5. Reservation timer
6. Simple analytics

## Goal

The target is this:

Can a boutique owner run the shop without needing manual SQL or constant intervention?
