"""
YourCloser — Database Layer
All Supabase queries live here. The bot NEVER guesses — it only reports what the DB says.
"""
from supabase import create_client, Client
from config import settings
from typing import Optional
from datetime import datetime, timezone


def get_client() -> Client:
    """Create and return a Supabase client using service role key."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


# ─── Product Queries ──────────────────────────────────────────────

def search_products(query: str, shop_id: str) -> list[dict]:
    """
    Search products by name (case-insensitive partial match).
    Returns list of matching products with their basic info.
    """
    client = get_client()
    result = (
        client.table("products")
        .select("id, name, description, image_url")
        .ilike("name", f"%{query}%")
        .eq("is_active", True)
        .eq("shop_id", shop_id)
        .limit(5)
        .execute()
    )
    return result.data


def get_product_by_id(product_id: str, shop_id: str) -> Optional[dict]:
    """Get a single product by ID, always enforcing the shop_id boundary."""
    client = get_client()
    result = (
        client.table("products")
        .select("id, name, description, image_url, category, shop_id")
        .eq("id", product_id)
        .eq("shop_id", shop_id)
        .single()
        .execute()
    )
    return result.data


def get_categories(shop_id: str) -> list[str]:
    """Get a list of all unique active categories."""
    client = get_client()
    result = (
        client.table("products")
        .select("category")
        .eq("is_active", True)
        .eq("shop_id", shop_id)
        .execute()
    )
    if not result.data:
        return []
    
    categories = set(item.get("category", "Uncategorized") for item in result.data if item.get("category"))
    return sorted(list(categories))


def get_products_by_category(category: str, shop_id: str) -> list[dict]:
    """Get active products for a specific category."""
    client = get_client()
    result = (
        client.table("products")
        .select("id, name, description, image_url")
        .eq("category", category)
        .eq("is_active", True)
        .eq("shop_id", shop_id)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_new_arrivals(limit: int, shop_id: str) -> list[dict]:
    """Get the latest active products."""
    client = get_client()
    result = (
        client.table("products")
        .select("id, name, description, image_url")
        .eq("is_active", True)
        .eq("shop_id", shop_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


def get_trending_products(limit: int, shop_id: str) -> list[dict]:
    """Get products with recent orders (trending)."""
    client = get_client()
    try:
        result = (
            client.table("orders")
            .select("product_id")
            .eq("shop_id", shop_id)
            .order("created_at", desc=True)
            .limit(15)
            .execute()
        )
        if result.data:
            from collections import Counter
            counts = Counter(item["product_id"] for item in result.data if item.get("product_id"))
            top_product_ids = [pid for pid, _ in counts.most_common(limit)]
            if top_product_ids:
                products_res = (
                    client.table("products")
                    .select("id, name, description, image_url")
                    .in_("id", top_product_ids)
                    .eq("is_active", True)
                    .eq("shop_id", shop_id)
                    .execute()
                )
                if products_res.data:
                    id_to_prod = {p["id"]: p for p in products_res.data}
                    return [id_to_prod[pid] for pid in top_product_ids if pid in id_to_prod]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching trending products: {e}")
    return get_new_arrivals(limit, shop_id)


def get_best_sellers(limit: int, shop_id: str) -> list[dict]:
    """Get products with most orders overall."""
    client = get_client()
    try:
        result = (
            client.table("orders")
            .select("product_id")
            .eq("shop_id", shop_id)
            .execute()
        )
        if result.data:
            from collections import Counter
            counts = Counter(item["product_id"] for item in result.data if item.get("product_id"))
            top_product_ids = [pid for pid, _ in counts.most_common(limit)]
            if top_product_ids:
                products_res = (
                    client.table("products")
                    .select("id, name, description, image_url")
                    .in_("id", top_product_ids)
                    .eq("is_active", True)
                    .eq("shop_id", shop_id)
                    .execute()
                )
                if products_res.data:
                    id_to_prod = {p["id"]: p for p in products_res.data}
                    return [id_to_prod[pid] for pid in top_product_ids if pid in id_to_prod]
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching best sellers: {e}")
    # Fallback to general active products list
    try:
        res = client.table("products").select("id, name, description, image_url").eq("is_active", True).eq("shop_id", shop_id).limit(limit).execute()
        return res.data if res.data else []
    except Exception:
        return []


def get_products_under_price(max_price: float, limit: int, shop_id: str) -> list[dict]:
    """Get products that have at least one stock item under max_price."""
    client = get_client()
    try:
        stock_res = (
            client.table("stock")
            .select("product_id")
            .lt("price", max_price)
            .gt("quantity", 0)
            .limit(50)
            .execute()
        )
        if stock_res.data:
            product_ids = list(set(item["product_id"] for item in stock_res.data))
            products_res = (
                client.table("products")
                .select("id, name, description, image_url")
                .in_("id", product_ids)
                .eq("is_active", True)
                .eq("shop_id", shop_id)
                .limit(limit)
                .execute()
            )
            return products_res.data
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error fetching products under price: {e}")
    return []


# ─── Stock Queries ────────────────────────────────────────────────

def check_stock(product_id: str, size: str, shop_id: str) -> Optional[dict]:
    """
    Check if a specific size is in stock for a product.
    Returns stock record if available, None if not found or out of stock.
    THE BOT NEVER GUESS — only returns what the DB says.
    """
    client = get_client()
    result = (
        client.table("stock")
        .select("id, product_id, size, quantity, price, products!inner(shop_id)")
        .eq("product_id", product_id)
        .eq("size", size.strip().upper())
        .eq("products.shop_id", shop_id)
        .gt("quantity", 0)
        .execute()
    )
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def get_available_sizes(product_id: str, shop_id: str) -> list[dict]:
    """Get all available sizes for a product (quantity > 0) belonging to the specified shop."""
    client = get_client()
    result = (
        client.table("stock")
        .select("size, quantity, price, products!inner(shop_id)")
        .eq("product_id", product_id)
        .eq("products.shop_id", shop_id)
        .gt("quantity", 0)
        .order("size")
        .execute()
    )
    return result.data


# NOTE: Old decrement_stock() removed — use decrement_stock_atomic() for race-condition safety


def decrement_stock_atomic(stock_id: str, shop_id: str) -> Optional[dict]:
    """
    Atomically decrement stock quantity by 1 for a given stock_id
    belonging to the specified shop using the PostgreSQL RPC.
    """
    client = get_client()
    # Verify stock ID belongs to correct shop first to enforce tenant separation
    stock_res = (
        client.table("stock")
        .select("id, products!inner(shop_id)")
        .eq("id", stock_id)
        .eq("products.shop_id", shop_id)
        .execute()
    )
    if not stock_res.data:
        return None
        
    result = client.rpc("decrement_stock_atomic", {"stock_id": stock_id}).execute()
    if result.data and len(result.data) > 0:
        return result.data[0] if isinstance(result.data, list) else result.data
    return None


# ─── Order Queries ────────────────────────────────────────────────

def create_order(
    product_id: str,
    product_name: str,
    size: str,
    price: float,
    customer_name: str,
    customer_phone: str,
    delivery_location: str,
    telegram_user_id: int,
    shop_id: str,
    telegram_username: Optional[str] = None,
) -> dict:
    """
    Save a new order to the database.
    Status starts as 'pending' — owner confirms manually.
    """
    client = get_client()
    order_data = {
        "product_id": product_id,
        "product_name": product_name,
        "size": size,
        "price": price,
        "customer_name": customer_name,
        "customer_phone": customer_phone,
        "delivery_location": delivery_location,
        "telegram_user_id": str(telegram_user_id),
        "telegram_username": telegram_username or "",
        "status": "pending",
        "shop_id": shop_id,
    }
    result = client.table("orders").insert(order_data).execute()
    return result.data[0] if result.data else {}


def update_order_status(order_id: str, status: str, shop_id: str) -> bool:
    """Update order status (pending → confirmed → delivered → cancelled) for a specific shop."""
    client = get_client()
    client.table("orders").update({"status": status}).eq("id", order_id).eq("shop_id", shop_id).execute()
    return True


def get_customer_profile(telegram_user_id: str, shop_id: str) -> Optional[dict]:
    """Get the customer's name, phone, and location from their most recent order in the specified shop."""
    client = get_client()
    result = (
        client.table("orders")
        .select("customer_name, customer_phone, delivery_location")
        .eq("telegram_user_id", str(telegram_user_id))
        .eq("shop_id", shop_id)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None


def get_user_orders(telegram_user_id: str, shop_id: str) -> list[dict]:
    """Get all recent orders for a user to show in 'Track Orders' for the specified shop."""
    client = get_client()
    result = (
        client.table("orders")
        .select("id, product_name, size, price, status, created_at")
        .eq("telegram_user_id", str(telegram_user_id))
        .eq("shop_id", shop_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    return result.data


def get_fulfilled_today_count(shop_id: str) -> int:
    """Fetch count of orders created today for the specified shop."""
    client = get_client()
    # Get the start of today in UTC
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    iso_start = today_start.isoformat()
    
    result = (
        client.table("orders")
        .select("id", count="exact")
        .eq("shop_id", shop_id)
        .gte("created_at", iso_start)
        .neq("status", "cancelled")
        .execute()
    )
    return result.count if result.count is not None else (len(result.data) if result.data else 0)

# Alias for backward compatibility with handlers
get_daily_order_count = get_fulfilled_today_count


# ─── Admin Queries ────────────────────────────────────────────────

def get_all_customers(shop_id: str) -> list[str]:
    """Get unique telegram user IDs for all past customers (for broadcasting) in the specified shop."""
    client = get_client()
    result = client.table("orders").select("telegram_user_id").eq("shop_id", shop_id).execute()
    if not result.data:
        return []
    # Extract unique IDs
    unique_ids = set(row["telegram_user_id"] for row in result.data if row.get("telegram_user_id"))
    return list(unique_ids)


def get_stats(shop_id: str) -> dict:
    """Get basic sales statistics for the specified shop."""
    client = get_client()
    result = client.table("orders").select("status, price").eq("shop_id", shop_id).execute()
    
    stats = {
        "total_orders": 0,
        "pending": 0,
        "confirmed": 0,
        "revenue": 0.0
    }
    
    if result.data:
        for row in result.data:
            stats["total_orders"] += 1
            if row["status"] == "pending":
                stats["pending"] += 1
            elif row["status"] == "confirmed":
                stats["confirmed"] += 1
                stats["revenue"] += float(row["price"])
                
    return stats


def add_product(name: str, description: str, category: str, image_url: str, shop_id: str) -> str:
    """Admin function: Create a new product and return its ID."""
    client = get_client()
    data = {
        "name": name,
        "description": description,
        "category": category,
        "image_url": image_url,
        "is_active": True,
        "shop_id": shop_id
    }
    result = client.table("products").insert(data).execute()
    return result.data[0]["id"]


def add_stock(product_id: str, size: str, quantity: int, price: float, shop_id: str) -> None:
    """Admin function: Add stock/size/price for a product, verifying it belongs to the shop."""
    client = get_client()
    # Verify product belongs to shop
    product = get_product_by_id(product_id, shop_id)
    if not product:
        raise ValueError(f"Product {product_id} not found or does not belong to shop {shop_id}")
    data = {
        "product_id": product_id,
        "size": size.strip().upper(),
        "quantity": quantity,
        "price": price
    }
    client.table("stock").insert(data).execute()
