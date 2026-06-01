"""
YourCloser — Chaos Test Suite
Validates concurrency guards, tenant isolation, and anti-spam mechanisms.
Run: python chaos_test.py
"""
import asyncio
import time
import sys
import os

# ─── Test Framework ──────────────────────────────────────────────
class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def ok(self, name):
        self.passed += 1
        print(f"  [OK] {name}")

    def fail(self, name, reason):
        self.failed += 1
        self.errors.append((name, reason))
        print(f"  [FAIL] {name}: {reason}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*50}")
        print(f"Results: {self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailures:")
            for name, reason in self.errors:
                print(f"  - {name}: {reason}")
        print(f"{'='*50}")
        return self.failed == 0


results = TestResult()


# ═══════════════════════════════════════════════════════════════════
# TEST 1: Import validation — all modules load without errors
# ═══════════════════════════════════════════════════════════════════
def test_imports():
    print("\n[TEST 1] Import Validation")
    try:
        import db
        results.ok("db.py imports cleanly")
    except Exception as e:
        results.fail("db.py import", str(e))

    try:
        import tenant_context
        results.ok("tenant_context.py imports cleanly")
    except Exception as e:
        results.fail("tenant_context.py import", str(e))

    try:
        import handlers
        results.ok("handlers.py imports cleanly")
    except Exception as e:
        results.fail("handlers.py import", str(e))

    try:
        import config
        results.ok("config.py imports cleanly")
    except Exception as e:
        results.fail("config.py import", str(e))


# ═══════════════════════════════════════════════════════════════════
# TEST 2: Checkout lock (anti-duplicate submission)
# ═══════════════════════════════════════════════════════════════════
def test_checkout_lock():
    print("\n[TEST 2] Checkout Lock (Anti-Duplicate Submission)")
    from handlers import acquire_order_lock, release_order_lock

    user_id = 12345

    # First acquisition should succeed
    assert acquire_order_lock(user_id), "First lock acquisition failed"
    results.ok("First lock acquired")

    # Second acquisition should FAIL (user already locked)
    assert not acquire_order_lock(user_id), "Duplicate lock was not blocked"
    results.ok("Duplicate lock blocked")

    # Release and re-acquire
    release_order_lock(user_id)
    assert acquire_order_lock(user_id), "Lock not released properly"
    results.ok("Lock released and re-acquired")

    release_order_lock(user_id)


# ═══════════════════════════════════════════════════════════════════
# TEST 3: Rapid-fire spam lock (10x concurrent attempts)
# ═══════════════════════════════════════════════════════════════════
def test_spam_lock():
    print("\n[TEST 3] Rapid-Fire Spam Lock (10x Concurrent)")
    from handlers import acquire_order_lock, release_order_lock

    user_id = 99999
    acquired_count = 0

    # Simulate 10 rapid clicks
    for _ in range(10):
        if acquire_order_lock(user_id):
            acquired_count += 1

    if acquired_count == 1:
        results.ok(f"Only 1 of 10 rapid clicks acquired the lock")
    else:
        results.fail("Spam lock", f"Expected 1 acquisition, got {acquired_count}")

    release_order_lock(user_id)


# ═══════════════════════════════════════════════════════════════════
# TEST 4: db.py function signatures require shop_id
# ═══════════════════════════════════════════════════════════════════
def test_db_signatures():
    print("\n[TEST 4] DB Functions Require Explicit shop_id")
    import inspect
    import db

    # Functions that MUST have 'shop_id' as a required (non-default) parameter
    must_have_shop_id = [
        "search_products",
        "get_product_by_id",
        "get_categories",
        "get_products_by_category",
        "get_new_arrivals",
        "get_trending_products",
        "get_best_sellers",
        "check_stock",
        "get_available_sizes",
        "decrement_stock_atomic",
        "create_order",
        "update_order_status",
        "get_customer_profile",
        "get_user_orders",
        "get_fulfilled_today_count",
        "get_all_customers",
        "get_stats",
        "add_product",
        "add_stock",
    ]

    for fn_name in must_have_shop_id:
        fn = getattr(db, fn_name, None)
        if fn is None:
            results.fail(f"db.{fn_name}", "Function not found")
            continue

        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())

        if "shop_id" in params:
            # Check it's not optional with a default
            param = sig.parameters["shop_id"]
            if param.default is inspect.Parameter.empty:
                results.ok(f"db.{fn_name}() - shop_id is required")
            else:
                results.fail(f"db.{fn_name}()", f"shop_id has default='{param.default}' - must be required")
        else:
            results.fail(f"db.{fn_name}()", "Missing shop_id parameter entirely")


# ═══════════════════════════════════════════════════════════════════
# TEST 5: Old decrement_stock is REMOVED
# ═══════════════════════════════════════════════════════════════════
def test_old_decrement_removed():
    print("\n[TEST 5] Old decrement_stock() Removed")
    import db
    import inspect

    if hasattr(db, "decrement_stock") and callable(db.decrement_stock):
        sig = inspect.signature(db.decrement_stock)
        params = list(sig.parameters.keys())
        if "current_qty" in params:
            results.fail("decrement_stock", "Old non-atomic decrement_stock() still exists with current_qty param")
        else:
            results.ok("decrement_stock is either removed or replaced")
    else:
        results.ok("Old decrement_stock() is removed")


# ═══════════════════════════════════════════════════════════════════
# TEST 6: get_daily_order_count alias exists
# ═══════════════════════════════════════════════════════════════════
def test_daily_order_alias():
    print("\n[TEST 6] get_daily_order_count Alias")
    import db

    if hasattr(db, "get_daily_order_count"):
        if db.get_daily_order_count is db.get_fulfilled_today_count:
            results.ok("get_daily_order_count is alias for get_fulfilled_today_count")
        else:
            results.fail("get_daily_order_count", "Exists but is NOT the same function as get_fulfilled_today_count")
    else:
        results.fail("get_daily_order_count", "Alias not found in db.py")


# ═══════════════════════════════════════════════════════════════════
# TEST 7: Tenant context guard returns string
# ═══════════════════════════════════════════════════════════════════
def test_tenant_context():
    print("\n[TEST 7] Tenant Context Guard")
    import tenant_context

    # Test with None context - should return "default" without crashing
    class FakeUpdate:
        effective_user = type("U", (), {"id": 1})()
        message = None
        callback_query = None

    class FakeContext:
        user_data = {}
        args = None

    result = tenant_context.get_shop_id(FakeUpdate(), FakeContext())
    if isinstance(result, str) and result == "default":
        results.ok("Fallback to 'default' works")
    else:
        results.fail("Tenant fallback", f"Expected 'default', got '{result}'")

    # Test with cached shop_id
    ctx = FakeContext()
    ctx.user_data = {"shop_id": "test_store_123"}
    result = tenant_context.get_shop_id(FakeUpdate(), ctx)
    if result == "test_store_123":
        results.ok("Cached shop_id returned correctly")
    else:
        results.fail("Tenant cached", f"Expected 'test_store_123', got '{result}'")


# ═══════════════════════════════════════════════════════════════════
# TEST 8: handlers.py doesn't call non-existent db functions
# ═══════════════════════════════════════════════════════════════════
def test_handler_db_calls():
    print("\n[TEST 8] Handler -> DB Call Integrity")

    with open("handlers.py", "r", encoding="utf-8") as f:
        source = f.read()

    # These function calls should NOT exist in handlers.py
    banned_calls = [
        "db.decrement_stock(",  # Old non-atomic - should be decrement_stock_atomic
    ]

    for call in banned_calls:
        # Make sure it's not calling the old version (but atomic is OK)
        if call in source and "decrement_stock_atomic" not in source.split(call)[0].split("\n")[-1]:
            import re
            matches = re.findall(r'db\.decrement_stock\((?!atomic)', source)
            if matches:
                results.fail(f"Banned call: {call}", f"Found {len(matches)} instances of old decrement_stock()")
            else:
                results.ok(f"No banned call: {call}")
        else:
            results.ok(f"No banned call: {call}")

    # These MUST exist
    required_calls = [
        "db.decrement_stock_atomic(",
        "db.get_fulfilled_today_count(",
        "tenant_context.get_shop_id(",
    ]

    for call in required_calls:
        if call in source:
            results.ok(f"Required call present: {call}")
        else:
            results.fail(f"Missing call: {call}", "Not found in handlers.py")


# ═══════════════════════════════════════════════════════════════════
# TEST 9: Concurrent lock stress test (async)
# ═══════════════════════════════════════════════════════════════════
async def test_concurrent_locks():
    print("\n[TEST 9] Concurrent Lock Stress Test (Async)")
    from handlers import acquire_order_lock, release_order_lock

    acquired = []

    async def try_acquire(user_id, attempt):
        # Simulate slight timing offset
        await asyncio.sleep(0.001 * attempt)
        if acquire_order_lock(user_id):
            acquired.append(attempt)

    user_id = 77777
    tasks = [try_acquire(user_id, i) for i in range(20)]
    await asyncio.gather(*tasks)

    if len(acquired) == 1:
        results.ok(f"20 concurrent attempts -> only 1 acquired (attempt #{acquired[0]})")
    else:
        results.fail("Concurrent lock", f"Expected 1 acquisition, got {len(acquired)}: {acquired}")

    release_order_lock(user_id)


# ═══════════════════════════════════════════════════════════════════
# TEST 10: Deep Funnel Funnel Resolution & Tenant Transition
# ═══════════════════════════════════════════════════════════════════
def test_deep_link_funnel():
    print("\n[TEST 10] Deep Link Funnel Resolution & Tenant Transition")
    import tenant_context
    from unittest.mock import patch

    fake_product = {
        "id": "123456",
        "name": "Super Sneaker",
        "shop_id": "urbankicks"
    }

    class FakeUser:
        id = 42
        username = "tester"

    class FakeMessage:
        text = "/start urbankicks_p_123456"

    class FakeUpdate:
        effective_user = FakeUser()
        message = FakeMessage()
        callback_query = None

    class FakeContext:
        user_data = {}
        args = None

    # Test 10a: Composite link /start urbankicks_p_123456
    ctx = FakeContext()
    shop_id = tenant_context.get_shop_id(FakeUpdate(), ctx)
    if shop_id == "urbankicks" and ctx.user_data.get("deep_product_id") == "123456":
        results.ok("Composite deep link resolved shop_id and deep_product_id correctly")
    else:
        results.fail("Composite deep link", f"Expected shop_id='urbankicks', got '{shop_id}'; deep_product_id='123456', got '{ctx.user_data.get('deep_product_id')}'")

    # Test 10b: Global link /start p_123456
    class FakeMessageGlobal:
        text = "/start p_123456"

    class FakeUpdateGlobal:
        effective_user = FakeUser()
        message = FakeMessageGlobal()
        callback_query = None

    ctx_global = FakeContext()
    with patch("db.get_product_by_id_global", return_value=fake_product):
        shop_id_global = tenant_context.get_shop_id(FakeUpdateGlobal(), ctx_global)
        if shop_id_global == "urbankicks" and ctx_global.user_data.get("deep_product_id") == "123456":
            results.ok("Global deep link resolved shop_id and deep_product_id correctly")
        else:
            results.fail("Global deep link", f"Expected shop_id='urbankicks', got '{shop_id_global}'; deep_product_id='123456', got '{ctx_global.user_data.get('deep_product_id')}'")


# ═══════════════════════════════════════════════════════════════════
# TEST 11: White-label Branding Integration
# ═══════════════════════════════════════════════════════════════════
def test_whitelabel_branding():
    print("\n[TEST 11] White-label Branding Integration")
    import db

    # 1. Test fallback / default shop details
    details_default = db.get_shop_details("default")
    if details_default and details_default.get("name") == "YourCloser" and details_default.get("theme_emoji") == "💎":
        results.ok("Default shop branding loaded correctly")
    else:
        results.fail("Default shop branding", f"Loaded incorrect details: {details_default}")

    # 2. Test fallback details for other stores (dynamic defaults)
    details_other = db.get_shop_details("randomstore")
    if details_other and details_other.get("name") == "Randomstore Store" and details_other.get("theme_emoji") == "💎":
        results.ok("Random store fallback branding loaded correctly")
    else:
        results.fail("Random store fallback branding", f"Loaded incorrect details: {details_other}")


# ═══════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════
def main():
    print("=" * 50)
    print("YourCloser Chaos Test Suite")
    print("=" * 50)

    test_imports()
    test_checkout_lock()
    test_spam_lock()
    test_db_signatures()
    test_old_decrement_removed()
    test_daily_order_alias()
    test_tenant_context()
    test_handler_db_calls()
    asyncio.run(test_concurrent_locks())
    test_deep_link_funnel()
    test_whitelabel_branding()

    success = results.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
