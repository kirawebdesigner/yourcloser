# Admin And Shop Setup

This is the owner workflow.

## Owner Access

Only the Telegram user ID in `TELEGRAM_OWNER_CHAT_ID` can use owner commands.

## Commands

- `/admin` opens the operational panel
- `/create_shop` starts the Telegram shop setup wizard

## `/admin` Flow

1. Owner opens `/admin`
2. Bot shows boutiques assigned to that owner
3. Owner selects one boutique
4. Bot pins `active_admin_shop_id`
5. All admin actions use that shop

## Admin Actions

- Add product
- Broadcast message
- Switch shop
- Close panel

## Product Creation

The product add flow supports:

- product photo
- product name
- description
- category
- sizes or options
- price
- quantity

It also supports a shortcut where a caption can be auto-parsed.

## Shop Creation

The `/create_shop` wizard collects:

- shop name
- delivery text
- support link
- theme emoji
- welcome text

Then it:

- creates the shop
- assigns the owner in `shop_admins`
- returns the customer link
