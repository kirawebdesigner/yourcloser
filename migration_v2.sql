-- =====================================================
-- YourCloser v2: Add categories + product images
-- Run this in Supabase SQL Editor AFTER schema.sql
-- =====================================================

-- Add category column
ALTER TABLE products ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'Uncategorized';

-- Update demo products with categories and real image URLs
UPDATE products SET category = 'Shoes', image_url = 'https://images.unsplash.com/photo-1549298916-b41d501d3772?w=400&h=300&fit=crop' WHERE name = 'Nike Air Force 1';
UPDATE products SET category = 'Shoes', image_url = 'https://images.unsplash.com/photo-1588361861040-ac9b1018f6d5?w=400&h=300&fit=crop' WHERE name = 'Adidas Yeezy Boost 350';
UPDATE products SET category = 'Shoes', image_url = 'https://images.unsplash.com/photo-1556906781-9a412961c28c?w=400&h=300&fit=crop' WHERE name = 'Jordan 1 Retro High';
UPDATE products SET category = 'Shoes', image_url = 'https://images.unsplash.com/photo-1539185441755-769473a23570?w=400&h=300&fit=crop' WHERE name = 'New Balance 550';
UPDATE products SET category = 'Shoes', image_url = 'https://images.unsplash.com/photo-1597045566677-8cf032ed6634?w=400&h=300&fit=crop' WHERE name = 'Nike Dunk Low';
