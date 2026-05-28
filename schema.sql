-- =====================================================
-- YourCloser: Consolidated Database Schema & Seed Data
-- =====================================================

-- Enable extensions FIRST (before any tables or indexes that need them)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Drop existing tables/types if you want a clean reset:
-- DROP TABLE IF EXISTS stock CASCADE;
-- DROP TABLE IF EXISTS orders CASCADE;
-- DROP TABLE IF EXISTS products CASCADE;
-- DROP TYPE IF EXISTS order_status CASCADE;

-- ─── Products Table ──────────────────────────────────
-- The catalog of items the shop sells
CREATE TABLE IF NOT EXISTS products (
    id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT DEFAULT 'Uncategorized',
    image_url TEXT,
    shop_id TEXT DEFAULT 'default',
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
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
        CREATE TYPE order_status AS ENUM ('pending', 'confirmed', 'delivered', 'cancelled');
    END IF;
END$$;

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
    shop_id TEXT DEFAULT 'default',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Indexes ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_products_name ON products USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_products_active ON products (is_active);
CREATE INDEX IF NOT EXISTS idx_products_shop_id ON products(shop_id);
CREATE INDEX IF NOT EXISTS idx_stock_product ON stock (product_id);
CREATE INDEX IF NOT EXISTS idx_stock_product_size ON stock (product_id, size);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_orders_shop_id ON orders(shop_id);
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders (created_at DESC);

-- ─── Updated At Trigger ─────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER stock_updated_at
    BEFORE UPDATE ON stock
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER orders_updated_at
    BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─── RLS Policies ────────────────────────────────────
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist to prevent errors on rerun
DROP POLICY IF EXISTS "Service role full access on products" ON products;
DROP POLICY IF EXISTS "Service role full access on stock" ON stock;
DROP POLICY IF EXISTS "Service role full access on orders" ON orders;

-- Allow service role full access (bot backend)
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
-- SEED DATA: Populate Catalog and Stock
-- =====================================================

-- Insert Shoes
INSERT INTO products (name, description, category, image_url, shop_id) VALUES
    ('Nike Air Force 1', 'Classic white leather sneaker', 'Shoes', 'https://images.unsplash.com/photo-1549298916-b41d501d3772?w=400&h=300&fit=crop', 'default'),
    ('Adidas Yeezy Boost 350', 'Cream white knit runner', 'Shoes', 'https://images.unsplash.com/photo-1588361861040-ac9b1018f6d5?w=400&h=300&fit=crop', 'default'),
    ('Jordan 1 Retro High', 'Chicago colorway, iconic red/white/black', 'Shoes', 'https://images.unsplash.com/photo-1556906781-9a412961c28c?w=400&h=300&fit=crop', 'default'),
    ('New Balance 550', 'White green, retro basketball silhouette', 'Shoes', 'https://images.unsplash.com/photo-1539185441755-769473a23570?w=400&h=300&fit=crop', 'default'),
    ('Nike Dunk Low', 'Panda colorway, black and white', 'Shoes', 'https://images.unsplash.com/photo-1597045566677-8cf032ed6634?w=400&h=300&fit=crop', 'default');

-- Insert Hoodies & Tech
INSERT INTO products (name, description, category, image_url, shop_id) VALUES 
    ('Essential Oversized Hoodie', 'Premium cotton blend, perfect for winter.', 'Hoodies', 'https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=400&h=300&fit=crop', 'default'),
    ('Nike Tech Fleece', 'Lightweight warmth and sleek style.', 'Hoodies', 'https://images.unsplash.com/photo-1614031679232-2cbac62e2402?w=400&h=300&fit=crop', 'default'),
    ('iPhone 15 Pro Max', '256GB, Natural Titanium. Brand new.', 'Tech', 'https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=400&h=300&fit=crop', 'default'),
    ('AirPods Pro (2nd Gen)', 'Active noise cancellation.', 'Tech', 'https://images.unsplash.com/photo-1600294037681-c80b4cb5b434?w=400&h=300&fit=crop', 'default');

-- Insert stock for each product dynamically
DO $$
DECLARE
    af1_id UUID;
    yeezy_id UUID;
    jordan_id UUID;
    nb_id UUID;
    dunk_id UUID;
    hoodie_id UUID;
    tech_fleece_id UUID;
    iphone_id UUID;
    airpods_id UUID;
BEGIN
    SELECT id INTO af1_id FROM products WHERE name = 'Nike Air Force 1';
    SELECT id INTO yeezy_id FROM products WHERE name = 'Adidas Yeezy Boost 350';
    SELECT id INTO jordan_id FROM products WHERE name = 'Jordan 1 Retro High';
    SELECT id INTO nb_id FROM products WHERE name = 'New Balance 550';
    SELECT id INTO dunk_id FROM products WHERE name = 'Nike Dunk Low';
    SELECT id INTO hoodie_id FROM products WHERE name = 'Essential Oversized Hoodie';
    SELECT id INTO tech_fleece_id FROM products WHERE name = 'Nike Tech Fleece';
    SELECT id INTO iphone_id FROM products WHERE name = 'iPhone 15 Pro Max';
    SELECT id INTO airpods_id FROM products WHERE name = 'AirPods Pro (2nd Gen)';

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

    -- Essential Hoodie stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (hoodie_id, 'M', 5, 2500),
        (hoodie_id, 'L', 3, 2500),
        (hoodie_id, 'XL', 2, 2500);

    -- Nike Tech Fleece stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (tech_fleece_id, 'M', 4, 3200),
        (tech_fleece_id, 'L', 1, 3200);

    -- iPhone stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (iphone_id, '256GB', 2, 140000);

    -- AirPods stock
    INSERT INTO stock (product_id, size, quantity, price) VALUES
        (airpods_id, 'Standard', 10, 18000);
END $$;
