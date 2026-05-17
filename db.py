"""
YourCloser — Database Layer
All Supabase queries live here. The bot NEVER guesses — it only reports what the DB says.
"""
from supabase import create_client, Client
from config import settings
from typing import Optional


def get_client() -> Client:
    """Create and return a Supabase client using service role key."""
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)


# ─── Product Queries ──────────────────────────────────────────────

def search_products(query: str) -> list[dict]:
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
        .limit(5)
        .execute()
    )
    return result.data


def get_product_by_id(product_id: str) -> Optional[dict]:
    """Get a single product by ID."""
    client = get_client()
    result = (
        client.table("products")
        .select("id, name, description, image_url, category")
        .eq("id", product_id)
        .single()
        .execute()
    )
    return result.data


def get_categories() -> list[str]:
    """Get a list of all unique active categories."""
    client = get_client()
    # Supabase doesn't have a distinct() method in the JS/Py client directly for simple columns,
    # so we fetch active products and extract unique categories.
    result = (
        client.table("products")
        .select("category")
        .eq("is_active", True)
        .execute()
    )
    if not result.data:
        return []
    
    categories = set(item.get("category", "Uncategorized") for item in result.data if item.get("category"))
    return sorted(list(categories))


def get_products_by_category(category: str) -> list[dict]:
    """Get active products for a specific category."""
    client = get_client()
    result = (
        client.table("products")
        .select("id, name, description, image_url")
        .eq("category", category)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )
    return result.data


def get_new_arrivals(limit: int = 5) -> list[dict]:
    """Get the latest active products."""
    client = get_client()
    result = (
        client.table("products")
        .select("id, name, description, image_url")
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data


# ─── Stock Queries ────────────────────────────────────────────────

def check_stock(product_id: str, size: str) -> Optional[dict]:
    """
    Check if a specific size is in stock for a product.
    Returns stock record if available, None if not found or out of stock.
    THE BOT NEVER GUESSES — only returns what the DB says.
    """
    client = get_client()
    result = (
        client.table("stock")
        .select("id, product_id, size, quantity, price")
        .eq("product_id", product_id)
        .eq("size", size.strip().upper())
        .gt("quantity", 0)
        .execute()
    )
    if result.data and len(result.data) > 0:
        return result.data[0]
    return None


def get_available_sizes(product_id: str) -> list[str]:
    """Get all available sizes for a product (quantity > 0)."""
    client = get_client()
    result = (
        client.table("stock")
        .select("size, quantity, price")
        .eq("product_id", product_id)
        .gt("quantity", 0)
        .order("size")
        .execute()
    )
    return result.data


def decrement_stock(stock_id: str, current_qty: int) -> bool:
    """
    Decrement stock by 1 after order confirmation.
    Uses current_qty for safety — won't go below 0.
    """
    if current_qty <= 0:
        return False
    client = get_client()
    client.table("stock").update({"quantity": current_qty - 1}).eq("id", stock_id).execute()
    return True


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
    }
    result = client.table("orders").insert(order_data).execute()
    return result.data[0] if result.data else {}


def update_order_status(order_id: str, status: str) -> bool:
    """Update order status (pending → confirmed → delivered → cancelled)."""
    client = get_client()
    client.table("orders").update({"status": status}).eq("id", order_id).execute()
    return True

def get_customer_profile(telegram_user_id: str) -> Optional[dict]:
    """Get the customer's name, phone, and location from their most recent order."""
    client = get_client()
    result = (
        client.table("orders")
        .select("customer_name, customer_phone, delivery_location")
        .eq("telegram_user_id", str(telegram_user_id))
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]
    return None

def get_user_orders(telegram_user_id: str) -> list[dict]:
    """Get all recent orders for a user to show in 'Track Orders'."""
    client = get_client()
    result = (
        client.table("orders")
        .select("id, product_name, size, price, status, created_at")
        .eq("telegram_user_id", str(telegram_user_id))
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    return result.data

# ─── Admin Queries ────────────────────────────────────────────────

def get_all_customers() -> list[str]:
    """Get unique telegram user IDs for all past customers (for broadcasting)."""
    client = get_client()
    result = client.table("orders").select("telegram_user_id").execute()
    if not result.data:
        return []
    # Extract unique IDs
    unique_ids = set(row["telegram_user_id"] for row in result.data if row.get("telegram_user_id"))
    return list(unique_ids)

def get_stats() -> dict:
    """Get basic sales statistics."""
    client = get_client()
    result = client.table("orders").select("status, price").execute()
    
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

def add_product(name: str, description: str, category: str, image_url: str) -> str:
    """Admin function: Create a new product and return its ID."""
    client = get_client()
    data = {
        "name": name,
        "description": description,
        "category": category,
        "image_url": image_url,
        "is_active": True
    }
    result = client.table("products").insert(data).execute()
    return result.data[0]["id"]

def add_stock(product_id: str, size: str, quantity: int, price: float) -> None:
    """Admin function: Add stock/size/price for a product."""
    client = get_client()
    data = {
        "product_id": product_id,
        "size": size,
        "quantity": quantity,
        "price": price
    }
    client.table("stock").insert(data).execute()

