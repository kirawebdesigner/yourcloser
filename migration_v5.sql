-- =====================================================
-- Migration V5: Atomic Stock Decrement & Helper RPCs
-- =====================================================

-- Atomically decrement stock quantity by 1 for a given stock_id,
-- checking that the quantity is > 0, and return the updated stock row.
CREATE OR REPLACE FUNCTION decrement_stock_atomic(stock_id UUID)
RETURNS SETOF stock AS $$
BEGIN
    RETURN QUERY
    UPDATE stock
    SET quantity = quantity - 1,
        updated_at = NOW()
    WHERE id = stock_id AND quantity > 0
    RETURNING *;
END;
$$ LANGUAGE plpgsql;
