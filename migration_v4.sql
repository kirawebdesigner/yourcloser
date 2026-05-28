-- =====================================================
-- YourCloser v4: Multi-tenant Readiness (shop_id support)
-- Run this in the Supabase SQL Editor
-- =====================================================

-- 1. Add shop_id to products table
ALTER TABLE products 
ADD COLUMN IF NOT EXISTS shop_id TEXT DEFAULT 'default';

-- 2. Add shop_id to orders table
ALTER TABLE orders 
ADD COLUMN IF NOT EXISTS shop_id TEXT DEFAULT 'default';

-- 3. Create indexes on shop_id for fast filtering
CREATE INDEX IF NOT EXISTS idx_products_shop_id ON products(shop_id);
CREATE INDEX IF NOT EXISTS idx_orders_shop_id ON orders(shop_id);

-- 4. Update any existing data to have 'default' shop_id (already set as default, but for assurance)
UPDATE products SET shop_id = 'default' WHERE shop_id IS NULL;
UPDATE orders SET shop_id = 'default' WHERE shop_id IS NULL;
