-- =====================================================
-- YourCloser v9: Client Plan Assignment & Enforcement
-- Run this in Supabase SQL Editor after migration_v8.sql
-- =====================================================

ALTER TABLE shops
ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'starter',
ADD COLUMN IF NOT EXISTS plan_status TEXT NOT NULL DEFAULT 'active',
ADD COLUMN IF NOT EXISTS billing_started_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS billing_renews_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS custom_limits JSONB DEFAULT '{}'::jsonb;

ALTER TABLE shops
DROP CONSTRAINT IF EXISTS shops_plan_check;

ALTER TABLE shops
ADD CONSTRAINT shops_plan_check
CHECK (plan IN ('starter', 'growth', 'pro', 'custom'));

ALTER TABLE shops
DROP CONSTRAINT IF EXISTS shops_plan_status_check;

ALTER TABLE shops
ADD CONSTRAINT shops_plan_status_check
CHECK (plan_status IN ('trialing', 'active', 'past_due', 'paused', 'cancelled'));

CREATE INDEX IF NOT EXISTS idx_shops_plan ON shops(plan);
CREATE INDEX IF NOT EXISTS idx_shops_plan_status ON shops(plan_status);

UPDATE shops
SET plan = COALESCE(plan, 'starter'),
    plan_status = COALESCE(plan_status, 'active'),
    custom_limits = COALESCE(custom_limits, '{}'::jsonb);
