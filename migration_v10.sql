-- =====================================================
-- YourCloser v10: Atomic Multi-Item Checkout
-- Run this in Supabase SQL Editor after migration_v9.sql
-- =====================================================

CREATE OR REPLACE FUNCTION submit_checkout_atomic(
    p_shop_id TEXT,
    p_parent_order_id UUID,
    p_customer_name TEXT,
    p_customer_phone TEXT,
    p_delivery_location TEXT,
    p_telegram_user_id TEXT,
    p_telegram_username TEXT,
    p_items JSONB
)
RETURNS SETOF orders AS $$
DECLARE
    item JSONB;
    stock_check RECORD;
    inserted_order orders%ROWTYPE;
BEGIN
    IF p_items IS NULL OR jsonb_typeof(p_items) <> 'array' OR jsonb_array_length(p_items) = 0 THEN
        RAISE EXCEPTION 'checkout_items_empty';
    END IF;

    -- Validate every cart line belongs to the requested shop and product before mutating stock.
    FOR item IN SELECT value FROM jsonb_array_elements(p_items)
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM stock s
            JOIN products p ON p.id = s.product_id
            WHERE s.id = (item->>'stock_id')::UUID
              AND s.product_id = (item->>'product_id')::UUID
              AND LOWER(s.size) = LOWER(item->>'size')
              AND p.shop_id = p_shop_id
              AND p.is_active = TRUE
        ) THEN
            RAISE EXCEPTION 'checkout_item_invalid_or_wrong_shop:%', item->>'stock_id';
        END IF;
    END LOOP;

    -- Lock each stock row once and verify enough quantity for duplicate cart lines too.
    FOR stock_check IN
        SELECT (value->>'stock_id')::UUID AS stock_id, COUNT(*)::INTEGER AS requested_qty
        FROM jsonb_array_elements(p_items)
        GROUP BY (value->>'stock_id')::UUID
    LOOP
        PERFORM 1
        FROM stock
        WHERE id = stock_check.stock_id
        FOR UPDATE;

        IF NOT EXISTS (
            SELECT 1
            FROM stock s
            JOIN products p ON p.id = s.product_id
            WHERE s.id = stock_check.stock_id
              AND p.shop_id = p_shop_id
              AND p.is_active = TRUE
              AND s.quantity >= stock_check.requested_qty
        ) THEN
            RAISE EXCEPTION 'checkout_stock_unavailable:%', stock_check.stock_id;
        END IF;
    END LOOP;

    -- All checks passed. Apply stock mutations.
    FOR stock_check IN
        SELECT (value->>'stock_id')::UUID AS stock_id, COUNT(*)::INTEGER AS requested_qty
        FROM jsonb_array_elements(p_items)
        GROUP BY (value->>'stock_id')::UUID
    LOOP
        UPDATE stock
        SET quantity = quantity - stock_check.requested_qty,
            updated_at = NOW()
        WHERE id = stock_check.stock_id;
    END LOOP;

    -- Insert order rows using DB-owned product name, size, and current price.
    FOR item IN SELECT value FROM jsonb_array_elements(p_items)
    LOOP
        INSERT INTO orders (
            product_id,
            product_name,
            size,
            price,
            customer_name,
            customer_phone,
            delivery_location,
            telegram_user_id,
            telegram_username,
            status,
            shop_id,
            parent_order_id
        )
        SELECT
            p.id,
            p.name,
            s.size,
            s.price,
            p_customer_name,
            p_customer_phone,
            p_delivery_location,
            p_telegram_user_id,
            COALESCE(p_telegram_username, ''),
            'pending',
            p_shop_id,
            p_parent_order_id
        FROM stock s
        JOIN products p ON p.id = s.product_id
        WHERE s.id = (item->>'stock_id')::UUID
          AND s.product_id = (item->>'product_id')::UUID
          AND p.shop_id = p_shop_id
          AND p.is_active = TRUE
        RETURNING * INTO inserted_order;

        IF inserted_order.id IS NULL THEN
            RAISE EXCEPTION 'checkout_order_insert_failed:%', item->>'stock_id';
        END IF;

        RETURN NEXT inserted_order;
    END LOOP;

    RETURN;
END;
$$ LANGUAGE plpgsql;
