-- =====================================================
-- YourCloser v7: Admin Shop Ownership & Explicit Switching
-- Run this in the Supabase SQL Editor after migration_v6.sql
-- =====================================================

CREATE TABLE IF NOT EXISTS shop_admins (
    shop_id TEXT NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
    telegram_user_id TEXT NOT NULL,
    role TEXT DEFAULT 'owner',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (shop_id, telegram_user_id)
);

CREATE INDEX IF NOT EXISTS idx_shop_admins_user ON shop_admins(telegram_user_id);

ALTER TABLE shop_admins ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service role full access on shop_admins" ON shop_admins;
CREATE POLICY "Service role full access on shop_admins" ON shop_admins FOR ALL USING (auth.role() = 'service_role');

-- After running this migration, assign boutiques to Telegram admins.
-- Replace the example Telegram user ID before running:
--
-- INSERT INTO shop_admins (shop_id, telegram_user_id, role)
-- VALUES ('urbankicks', '123456789', 'owner')
-- ON CONFLICT (shop_id, telegram_user_id) DO UPDATE SET role = EXCLUDED.role;
