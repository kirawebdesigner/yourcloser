# Customer Flow

This is the shopping flow from the customer side.

## Entry Points

- `/start`
- `/start <shop_id>`
- `/start <shop_id>_p_<product_id>`
- `/start p_<product_id>`

## Flow

1. Customer opens the bot
2. Bot resolves the shop context
3. Bot shows the branded storefront
4. Customer browses categories or search
5. Customer opens a product
6. Customer selects a size or option
7. Customer adds to cart or buys now
8. Customer checks out
9. Bot asks name, phone, and delivery location
10. Bot confirms the order summary
11. Bot atomically updates stock
12. Bot creates the order
13. Owner gets notified

## Safety Checks

- Stock is checked before showing the product
- Stock is checked again at size selection
- Stock is checked again at confirmation
- The final stock decrement is atomic

## Customer Experience Notes

- The bot shows product images when available
- The bot supports cart persistence
- The bot can remember prior checkout details
- The bot can show recent orders to the customer
