-- migration_v8.sql
-- 1. Add 'on_way' to the order_status enum
ALTER TYPE order_status ADD VALUE IF NOT EXISTS 'on_way' AFTER 'confirmed';

-- 2. Add 'parent_order_id' to orders table to group items checked out together
ALTER TABLE orders ADD COLUMN IF NOT EXISTS parent_order_id UUID;

-- 3. Add an index for performance
CREATE INDEX IF NOT EXISTS idx_orders_parent_order_id ON orders(parent_order_id);
