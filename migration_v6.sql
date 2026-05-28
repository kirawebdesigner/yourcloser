-- =====================================================
-- YourCloser v6: Boutique Branding & Identity Layer
-- Run this in the Supabase SQL Editor
-- =====================================================

CREATE TABLE IF NOT EXISTS shops (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    welcome_text TEXT,
    support_link TEXT,
    delivery_text TEXT,
    theme_emoji TEXT DEFAULT '💎',
    is_verified BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Ensure updated_at trigger is active on shops table
CREATE OR REPLACE TRIGGER shops_updated_at
    BEFORE UPDATE ON shops
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Enable RLS for shops
ALTER TABLE shops ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on shops" ON shops;
CREATE POLICY "Service role full access on shops" ON shops FOR ALL USING (auth.role() = 'service_role');

-- Insert default seed data
INSERT INTO shops (id, name, welcome_text, theme_emoji, is_verified)
VALUES (
    'default',
    'YourCloser',
    'Your premium 24/7 boutique assistant.',
    '💎',
    false
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    welcome_text = EXCLUDED.welcome_text,
    theme_emoji = EXCLUDED.theme_emoji,
    is_verified = EXCLUDED.is_verified;

INSERT INTO shops (id, name, welcome_text, support_link, delivery_text, theme_emoji, is_verified)
VALUES (
    'urbankicks',
    'UrbanKicks Addis',
    'Premium Sneaker Boutique. Same-Day Delivery in Addis Ababa. New drops every week!',
    'https://t.me/urbankicks_support',
    'Same-Day Delivery in Addis Ababa: 200 ETB.',
    '👟',
    true
) ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    welcome_text = EXCLUDED.welcome_text,
    support_link = EXCLUDED.support_link,
    delivery_text = EXCLUDED.delivery_text,
    theme_emoji = EXCLUDED.theme_emoji,
    is_verified = EXCLUDED.is_verified;
