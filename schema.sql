-- =====================================================
-- YourCloser: Database Schema for Supabase
-- Run this in the Supabase SQL Editor
-- =====================================================

-- Enable extensions FIRST (before any tables or indexes that need them)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─── Products Table ──────────────────────────────────
-- The catalog of items the shop sells
CREATE TABLE IF NOT EXISTS products (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    image_url TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Stock Table ─────────────────────────────────────
-- Per-size inventory tracking
-- Each row = one product + one size + quantity + price
CREATE TABLE IF NOT EXISTS stock (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    product_id UUID REFERENCES products(id) ON DELETE CASCADE,
    size TEXT NOT NULL,
    quantity INTEGER DEFAULT 0 CHECK (quantity >= 0),
    price NUMERIC(10, 2) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- One entry per product-size combo
    UNIQUE(product_id, size)
);

-- ─── Orders Table ────────────────────────────────────
-- Every order placed through the bot
CREATE TYPE order_status AS ENUM ('pending', 'confirmed', 'delivered', 'cancelled');

CREATE TABLE IF NOT EXISTS orders (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    product_id UUID REFERENCES products(id),
    product_name TEXT NOT NULL,
    size TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    delivery_location TEXT NOT NULL,
    telegram_user_id TEXT,
    telegram_username TEXT,
    status order_status DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Indexes (pg_trgm already enabled above) ────────
CREATE INDEX IF NOT EXISTS idx_products_name ON products USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_active ON products (is_active);
CREATE INDEX IF NOT EXISTS idx_stock_product ON stock (product_id);
CREATE INDEX IF NOT EXISTS idx_stock_product_size ON stock (product_id, size);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders (created_at DESC);

-- ─── Updated At Trigger ─────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER stock_updated_at
    BEFORE UPDATE ON stock
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── RLS Policies ────────────────────────────────────
-- Using service_role key from backend, so RLS is bypassed.
-- But enable it anyway for safety if anyone connects with anon key.
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (bot backend)
-- No anon policies = anon can't read/write anything directly
CREATE POLICY "Service role full access on products"
    ON products FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on stock"
    ON stock FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on orders"
    ON orders FOR ALL
    USING (auth.role() = 'service_role');

-- =====================================================
-- DEMO DATA: Fake sneaker store for testing
-- Remove this in production
-- =====================================================

INSERT INTO products (name, description, is_active) VALUES
    ('Nike Air Force 1', 'Classic white leather sneaker', true),
    ('Adidas Yeezy Boost 350', 'Cream white knit runner', true),
    ('Jordan 1 Retro High', 'Chicago colorway, iconic red/white/black', true),
    ('New Balance 550', 'White green, retro basketball silhouette', true),
    ('Nike Dunk Low', 'Panda colorway, black and white', true);

-- Insert stock for each product
-- Get product IDs dynamically
DO $$
DECLARE
    af1_id UUID;
    yeezy_id UUID;
    jordan_id UUID;
    nb_id UUID;
    dunk_id UUID;
BEGIN
    SELECT id INTO af1_id FROM products WHERE name = 'Nike Air Force 1';
    SELECT id INTO yeezy_id FROM products WHERE name = 'Adidas Yeezy Boost 350';
    SELECT id INTO jordan_id FROM products WHERE name = 'Jordan 1 Retro High';
    SELECT id INTO nb_id FROM products WHERE name = 'New Balance 550';
    SELECT id INTO dunk_id FROM products WHERE name = 'Nike Dunk Low';

    -- Air Force 1 stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (af1_id, '40', 3, 4500),
        (af1_id, '41', 5, 4500),
        (af1_id, '42', 2, 4500),
        (af1_id, '43', 0, 4500),
        (af1_id, '44', 1, 4500);

    -- Yeezy stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (yeezy_id, '40', 1, 12000),
        (yeezy_id, '41', 2, 12000),
        (yeezy_id, '42', 0, 12000),
        (yeezy_id, '43', 1, 12500);

    -- Jordan 1 stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (jordan_id, '41', 2, 8500),
        (jordan_id, '42', 3, 8500),
        (jordan_id, '43', 1, 8500),
        (jordan_id, '44', 0, 8500);

    -- NB 550 stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (nb_id, '40', 4, 5500),
        (nb_id, '41', 2, 5500),
        (nb_id, '42', 1, 5500),
        (nb_id, '43', 3, 5500);

    -- Dunk Low stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (dunk_id, '40', 0, 6000),
        (dunk_id, '41', 1, 6000),
        (dunk_id, '42', 2, 6000),
        (dunk_id, '43', 0, 6000),
        (dunk_id, '44', 3, 6000);
END $$;
