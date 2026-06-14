# Multi-Tenant And Roles

This project is built to serve multiple boutiques from one bot instance.

## Tenant Boundary

The key field is `shop_id`.

Every product, order, and admin action must resolve to a shop.

## Customer Context

Customer context is resolved in `tenant_context.py` from:

- deep links
- command arguments
- cached user session
- fallback `default`

## Admin Context

Admin context is separate from customer context.

The selected admin shop is stored in:

```python
context.user_data["active_admin_shop_id"]
```

That prevents the wrong shop from receiving product uploads or broadcasts.

## Role Model

Current roles are:

- `owner`
- `manager`
- `support`
- `staff`

The database currently stores the membership needed to grow into richer permissions later.

## Why This Matters

Without tenant separation:

- broadcasts can hit the wrong shop
- stock edits can hit the wrong catalog
- analytics become misleading
- ownership becomes impossible to reason about

With tenant separation:

- every action is deterministic
- scaling is safer
- auditing becomes possible
