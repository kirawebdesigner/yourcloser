-- =====================================================
-- YourCloser v3: Add diverse demo products
-- Run this in Supabase SQL Editor
-- =====================================================

-- 1. Insert New Products (Hoodies & Tech)
INSERT INTO products (name, description, category, image_url) VALUES 
('Essential Oversized Hoodie', 'Premium cotton blend, perfect for winter.', 'Hoodies', 'https://images.unsplash.com/photo-1556821840-3a63f95609a7?w=400&h=300&fit=crop'),
('Nike Tech Fleece', 'Lightweight warmth and sleek style.', 'Hoodies', 'https://images.unsplash.com/photo-1614031679232-2cbac62e2402?w=400&h=300&fit=crop'),
('iPhone 15 Pro Max', '256GB, Natural Titanium. Brand new.', 'Tech', 'https://images.unsplash.com/photo-1695048133142-1a20484d2569?w=400&h=300&fit=crop'),
('AirPods Pro (2nd Gen)', 'Active noise cancellation.', 'Tech', 'https://images.unsplash.com/photo-1600294037681-c80b4cb5b434?w=400&h=300&fit=crop');

-- 2. Add Stock for these products
-- We need to use subqueries to get the UUIDs of the products we just inserted.

-- Essential Hoodie (Sizes M, L, XL)
INSERT INTO stock (product_id, size, quantity, price)
SELECT id, 'M', 5, 2500 FROM products WHERE name = 'Essential Oversized Hoodie';
INSERT INTO stock (product_id, size, quantity, price)
SELECT id, 'L', 3, 2500 FROM products WHERE name = 'Essential Oversized Hoodie';
INSERT INTO stock (product_id, size, quantity, price)
SELECT id, 'XL', 2, 2500 FROM products WHERE name = 'Essential Oversized Hoodie';

-- Nike Tech Fleece (Sizes M, L)
INSERT INTO stock (product_id, size, quantity, price)
SELECT id, 'M', 4, 3200 FROM products WHERE name = 'Nike Tech Fleece';
INSERT INTO stock (product_id, size, quantity, price)
SELECT id, 'L', 1, 3200 FROM products WHERE name = 'Nike Tech Fleece';

-- iPhone 15 Pro Max (One "size" - 256GB)
INSERT INTO stock (product_id, size, quantity, price)
SELECT id, '256GB', 2, 140000 FROM products WHERE name = 'iPhone 15 Pro Max';

-- AirPods Pro
INSERT INTO stock (product_id, size, quantity, price)
SELECT id, 'Standard', 10, 18000 FROM products WHERE name = 'AirPods Pro (2nd Gen)';
