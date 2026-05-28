"""
YourCloser — Telegram Bot Handlers
Stateless Architecture for Serverless/Scale-to-Zero Deployment
"""
import logging
import asyncio
import time
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
    PicklePersistence
)
from telegram.error import BadRequest
from telegram.request import HTTPXRequest
from config import settings
import db
import tenant_context

logger = logging.getLogger(__name__)

# In-memory locks to prevent concurrent order submissions
_order_locks = set()

def acquire_order_lock(user_id: int) -> bool:
    """Acquire checkout lock for user_id to prevent duplicate order creations."""
    if user_id in _order_locks:
        return False
    _order_locks.add(user_id)
    return True

def release_order_lock(user_id: int) -> None:
    """Release checkout lock for user_id."""
    _order_locks.discard(user_id)



def update_activity(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track the user's last activity time and reset the recovery notification status."""
    context.user_data["last_activity"] = time.time()
    context.user_data["recovery_notified"] = False


async def typing_illusion(update: Update, context: ContextTypes.DEFAULT_TYPE, duration: float = 0.8) -> None:
    """Simulates the boutique typing to the customer for conversational immersion."""
    if not update or not update.effective_chat:
        return
    try:
        from telegram.constants import ChatAction
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
        await asyncio.sleep(duration)
    except Exception:
        pass


def parse_product_text(text: str) -> dict:
    """
    Parses a single text block into product details.
    Expected format examples:
    - Nike Dunk Low Grey, Category: Shoes, Sizes: 40, 41, 42, Price: 4800, Qty: 4
    - Jordan 1 Mid | Shoes | sizes: 41, 42, 43 | price: 7500 | qty: 5
    """
    data = {
        "name": None,
        "desc": "",
        "category": "Uncategorized",
        "sizes": [],
        "price": 0.0,
        "qty": 1
    }

    # Extract Price
    price_match = re.search(r'(?i)(?:price|💰|cost)[:\s]*([\d,]+)', text)
    if price_match:
        data["price"] = float(price_match.group(1).replace(",", ""))

    # Extract Quantity
    qty_match = re.search(r'(?i)(?:qty|quantity|📦|count|amt)[:\s]*(\d+)', text)
    if qty_match:
        data["qty"] = int(qty_match.group(1))

    # Extract Sizes
    sizes_match = re.search(r'(?i)(?:sizes|size|options|🏷️)[:\s]*([^,\n]+(?:,\s*[^,\n]+)*)', text)
    if sizes_match:
        sizes_str = sizes_match.group(1)
        # remove other fields if they got appended in the regex match
        sizes_str = re.sub(r'(?i)(?:price|qty|cat).*', '', sizes_str)
        raw_sizes = [s.strip() for s in sizes_str.split(",") if s.strip()]
        if len(raw_sizes) == 1 and " " in raw_sizes[0]:
            parts = [p.strip() for p in re.split(r'\s+', raw_sizes[0]) if p.strip()]
            data["sizes"] = parts if parts else raw_sizes
        else:
            data["sizes"] = raw_sizes
    else:
        # Fallback to look for size ranges or standard shoe size numbers
        nums = re.findall(r'\b(3[6-9]|4[0-9]|5[0-9]|M|L|XL|XXL|S)\b', text)
        if nums:
            data["sizes"] = list(set(nums))

    # Extract Category
    cat_match = re.search(r'(?i)(?:category|cat|tag)[:\s]*(\w+)', text)
    if cat_match:
        data["category"] = cat_match.group(1).strip().capitalize()
    else:
        # Infer category from text keywords
        for cat in ["Shoes", "Hoodies", "Tech", "Accessories"]:
            if cat.lower() in text.lower():
                data["category"] = cat
                break

    lines = [l.strip() for l in re.split(r'[,|\n]', text) if l.strip()]

    # Extract Name
    name_match = re.search(r'(?i)(?:name|title)[:\s]*([^\n,]+)', text)
    if name_match:
        data["name"] = name_match.group(1).strip()
    elif lines and ":" not in lines[0] and "=" not in lines[0]:
        data["name"] = lines[0].strip()
    else:
        first_part = re.split(r'(?i)(?:category|sizes|price|qty|desc|cat|options)', text)[0]
        data["name"] = first_part.strip().strip(",|-|:")

    # Extract Description
    desc_match = re.search(r'(?i)(?:desc|description)[:\s]*([^\n]+)', text)
    if desc_match:
        data["desc"] = desc_match.group(1).strip()
    elif len(lines) > 1 and ":" not in lines[1] and "sizes" not in lines[1].lower() and "price" not in lines[1].lower():
        data["desc"] = lines[1].strip()

    return data

# ─── Conversation States ─────────────────────────────────────────
(
    SEARCH_PRODUCT,
    CONFIRM_PROFILE,
    ENTER_NAME,
    ENTER_PHONE,
    ENTER_LOCATION,
    CONFIRM_ORDER,
    ADMIN_HOME,
    ADMIN_BROADCAST,
    ADMIN_ADD_PHOTO,
    ADMIN_ADD_NAME,
    ADMIN_ADD_DESC,
    ADMIN_ADD_CAT,
    ADMIN_ADD_SIZE,
    ADMIN_ADD_PRICE,
    ADMIN_ADD_QTY,
    ADMIN_CONFIRM_PROD
) = range(16)

CATEGORY_EMOJIS = {
    "Shoes": "👟",
    "Hoodies": "👕",
    "Accessories": "🧢",
    "Tech": "💻",
    "Uncategorized": "📦"
}

def get_emoji_for_category(cat: str) -> str:
    return CATEGORY_EMOJIS.get(cat, "📦")

async def safe_edit(query, text, markup=None, parse_mode="Markdown"):
    """Error handling: ignore duplicate taps that cause 'Message is not modified'"""
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            logger.error(f"Telegram error: {e}")

# ─── /start Command (Home Menu) ──────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    update_activity(context)
    if "cart" not in context.user_data: context.user_data["cart"] = []

    # Anti-spam: ignore duplicate taps if processing
    if context.user_data.get("user_state") == "processing":
        if update.callback_query:
            try:
                await update.callback_query.answer("⏳ Processing your order. Please wait...", show_alert=True)
            except Exception: pass
        return ConversationHandler.END

    # Extract dynamic tenant context
    shop_id = tenant_context.get_shop_id(update, context)

    # 🚀 Deep Product Funnel Intercept
    deep_product_id = context.user_data.pop("deep_product_id", None)
    if deep_product_id:
        prod = db.get_product_by_id_global(deep_product_id)
        if prod:
            # Force transition user's active tenant session to product's shop
            shop_id = prod.get("shop_id", "default")
            context.user_data["shop_id"] = shop_id
            logger.info(f"Funnels: Redirected user {update.effective_user.id if update and update.effective_user else '?'} to shop '{shop_id}' for product '{deep_product_id}'")

            # Setup list variables for carousel
            context.user_data["current_list"] = [prod]
            context.user_data["current_idx"] = 0
            context.user_data["list_title"] = "🔥 Direct Product Link"
            context.user_data["user_state"] = "browsing"

            # Render the product directly (non-edit fallback for start command)
            await render_product(update, context, edit_current=False)
            return ConversationHandler.END

    # Enforce browsing state
    context.user_data["user_state"] = "browsing"

    # Load dynamic boutique identity details
    shop_details = db.get_shop_details(shop_id)
    emoji = shop_details.get("theme_emoji", "💎")
    shop_name = shop_details.get("name", "YourCloser")
    welcome_text = shop_details.get("welcome_text", "Your premium 24/7 boutique assistant.")
    verified_badge = " ⚡ *Verified Store* ✅" if shop_details.get("is_verified") else ""

    keyboard = []

    # Smart Discovery Options (Shop Like a Human)
    keyboard.append([
        InlineKeyboardButton(f"{emoji} Trending Now", callback_data="discover_trending"),
        InlineKeyboardButton("⭐ Best Sellers", callback_data="discover_bestsellers")
    ])
    keyboard.append([
        InlineKeyboardButton("🆕 New Drops", callback_data="new_arrivals"),
        InlineKeyboardButton("⚡ Under 5,000 ETB", callback_data="discover_under5k")
    ])

    categories = db.get_categories(shop_id)
    row = []
    for cat in categories:
        cat_emoji = get_emoji_for_category(cat)
        row.append(InlineKeyboardButton(f"{cat_emoji} {cat}", callback_data=f"cat_{cat}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    keyboard.append([
        InlineKeyboardButton("🔍 Search", callback_data="search_mode"),
        InlineKeyboardButton("📦 Track Orders", callback_data="track_orders")
    ])

    support_link = shop_details.get("support_link")
    if support_link:
        keyboard.append([InlineKeyboardButton("💬 Contact Support", url=support_link)])

    if context.user_data.get("cart"):
        keyboard.append([InlineKeyboardButton(f"🛒 View Cart ({len(context.user_data['cart'])} items)", callback_data="view_cart")])

    text = (
        f"{emoji} *Welcome to {shop_name}!*{verified_badge}\n\n"
        f"{welcome_text}\n\n"
        f"Tap a discovery collection or category below to start browsing:"
    )

    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        query = update.callback_query
        await query.answer()
        if query.message.photo:
            await query.message.delete()
            await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
    return ConversationHandler.END


# ─── Handle Home Menu (Stateless) ────────────────────────────────
async def handle_home_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    update_activity(context)

    # Anti-spam state machine check
    if context.user_data.get("user_state") == "processing":
        try:
            await query.answer("⏳ Processing your order. Please wait...", show_alert=True)
        except Exception: pass
        return

    await query.answer()
    data = query.data

    # Enforce browsing state
    context.user_data["user_state"] = "browsing"

    # Extract dynamic tenant context
    shop_id = tenant_context.get_shop_id(update, context)

    if data == "track_orders":
        await typing_illusion(update, context)
        orders = db.get_user_orders(query.from_user.id, shop_id)
        if not orders:
            await safe_edit(query, "You haven't placed any orders yet!", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="nav_home")]]))
            return

        text = "📦 *Your Recent Orders*\n\n"
        for o in orders:
            status_emoji = {"pending": "⏳", "confirmed": "✅", "on_way": "🚚", "delivered": "📦", "cancelled": "❌"}.get(o['status'], "❓")
            text += f"{status_emoji} *{o['product_name']}* (Size {o['size']})\n"
            text += f"└ Status: {o['status'].title()} | {o['price']:,.0f} ETB\n\n"

        await safe_edit(query, text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data="nav_home")]]))
        return

    elif data == "view_cart":
        await show_cart(query, context)
        return

    products, title = [], ""
    if data.startswith("cat_"):
        cat = data.split("_", 1)[1]
        products = db.get_products_by_category(cat, shop_id)
        title = f"{get_emoji_for_category(cat)} *{cat} Collection*"
    elif data == "new_arrivals":
        products = db.get_new_arrivals(5, shop_id)
        title = "🆕 *New Drops*"
    elif data == "discover_trending":
        products = db.get_trending_products(5, shop_id)
        title = "🔥 *Trending Now*"
    elif data == "discover_bestsellers":
        products = db.get_best_sellers(5, shop_id)
        title = "💎 *Best Sellers*"
    elif data == "discover_under5k":
        products = db.get_products_under_price(5000, 5, shop_id)
        title = "⚡ *Under 5,000 ETB*"

    if not products:
        await query.answer("Nothing here yet!", show_alert=True)
        return

    context.user_data.update({"current_list": products, "current_idx": 0, "list_title": title})
    await render_product(query, context, edit_current=True)


# ─── Search Mode (Stateful) ──────────────────────────────────────
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query

    # Anti-spam state machine check
    if context.user_data.get("user_state") == "processing":
        try:
            await query.answer("⏳ Processing your order. Please wait...", show_alert=True)
        except Exception: pass
        return ConversationHandler.END

    await query.answer()

    # Enforce browsing state
    context.user_data["user_state"] = "browsing"

    await safe_edit(query, "🔍 *What are you looking for?*\n\n_Type the name of the product..._")
    return SEARCH_PRODUCT

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Anti-spam state machine check
    if context.user_data.get("user_state") == "processing":
        return ConversationHandler.END

    q = update.message.text.strip()
    if len(q) < 2: return SEARCH_PRODUCT

    # Enforce browsing state
    context.user_data["user_state"] = "browsing"

    # Extract dynamic tenant context
    shop_id = tenant_context.get_shop_id(update, context)

    await typing_illusion(update, context)

    products = db.search_products(q, shop_id)
    if not products:
        await update.message.reply_text(f"❌ Nothing found for \"{q}\". Try another keyword.")
        return SEARCH_PRODUCT

    context.user_data.update({"current_list": products, "current_idx": 0, "list_title": f"🔍 Search: {q}"})
    await render_product(update, context, edit_current=False)
    return ConversationHandler.END


# ─── Beautiful Product Carousel (Stateless) ──────────────────────
async def render_product(update_or_query, context: ContextTypes.DEFAULT_TYPE, edit_current: bool) -> None:
    update_activity(context)
    if "current_list" not in context.user_data or not context.user_data["current_list"]:
        # Safety catch if container restarted and memory was lost
        if isinstance(update_or_query, Update) and update_or_query.callback_query:
            await start(update_or_query, context)
        return

    idx = context.user_data["current_idx"]
    products = context.user_data["current_list"]
    product = products[idx]

    # Extract dynamic tenant context first — needed for all DB calls
    up = update_or_query if isinstance(update_or_query, Update) else None
    shop_id = tenant_context.get_shop_id(up, context)

    sizes = db.get_available_sizes(product["id"], shop_id)
    total_qty = sum(s.get("quantity", 0) for s in sizes)

    # Get daily order stats for trust badge
    daily_orders = db.get_fulfilled_today_count(shop_id)

    # Load dynamic boutique identity details
    shop_details = db.get_shop_details(shop_id)
    emoji = shop_details.get("theme_emoji", "💎")
    shop_name = shop_details.get("name", "YourCloser")
    verified_badge = " ⚡ *Verified Store* ✅" if shop_details.get("is_verified") else ""

    # Hashing-based deterministic social proof counters for realism
    import hashlib
    h = int(hashlib.md5(product["id"].encode()).hexdigest(), 16)
    views = (h % 35) + 15  # between 15 and 50 views
    orders_placed = (h % 5) + 2  # between 2 and 7 orders placed recently

    caption = f"📍 {context.user_data['list_title']}  ({idx + 1}/{len(products)})\n"
    caption += f"{emoji} *{shop_name}*{verified_badge} | ⚡ *Fast Delivery*\n"
    caption += f"👀 *{views} people viewed this today* | 🔥 *{orders_placed} ordered recently!*\n"
    if daily_orders > 0:
        caption += f"✨ *{daily_orders} successful checkouts today!*\n"
    caption += "\n"
    caption += f"✨ *{product['name']}*\n"


    if product.get('description'):
        caption += f"_{product['description']}_\n"

    caption += "\n"
    if sizes:
        prices = [s["price"] for s in sizes]
        price_display = f"{min(prices):,.0f} ETB" if min(prices) == max(prices) else f"{min(prices):,.0f} - {max(prices):,.0f} ETB"
        caption += f"💰 *Price:*  {price_display}\n"
        caption += f"🏷️ *Options:*  {', '.join([s['size'] for s in sizes])}\n"

        # Scarcity urgency signal
        if 0 < total_qty <= 3:
            caption += f"\n🔥 *Almost Sold Out! Only {total_qty} left!*\n"
    else:
        caption += f"🚫 *Currently Out of Stock*\n"

    # Dynamic share invite link for viral growth
    bot_username = context.bot.username
    share_url = f"https://t.me/{bot_username}?start={shop_id}_p_{product['id']}"
    share_button_url = f"https://t.me/share/url?url={share_url}&text=Check%20out%20this%20{product['name'].replace(' ', '%20')}!"

    keyboard = []
    if sizes:
        keyboard.append([
            InlineKeyboardButton("⚡ Buy Now", callback_data=f"buyfast_{product['id']}"),
            InlineKeyboardButton("🛒 Add to Cart", callback_data=f"buy_{product['id']}")
        ])

    keyboard.append([
        InlineKeyboardButton("🔗 Share Product", url=share_button_url)
    ])

    nav_row = []
    if len(products) > 1:
        nav_row.extend([InlineKeyboardButton("⬅️", callback_data="nav_prev"), InlineKeyboardButton("➡️", callback_data="nav_next")])
    if nav_row: keyboard.append(nav_row)

    bottom_row = [InlineKeyboardButton("🔙 Menu", callback_data="nav_home")]
    if context.user_data.get("cart"):
        bottom_row.append(InlineKeyboardButton(f"🛒 Cart ({len(context.user_data['cart'])})", callback_data="view_cart"))
    keyboard.append(bottom_row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    image_url = product.get("image_url")

    if isinstance(update_or_query, Update):
        if image_url: await update_or_query.message.reply_photo(photo=image_url, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)
        else: await update_or_query.message.reply_text(text=caption, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        query = update_or_query
        try:
            if image_url:
                try:
                    await query.message.delete()
                    await context.bot.send_photo(chat_id=query.message.chat_id, photo=image_url, caption=caption, parse_mode="Markdown", reply_markup=reply_markup)
                except BadRequest as e:
                    logger.warning(f"Image load failed: {e}. Falling back to text.")
                    await context.bot.send_message(chat_id=query.message.chat_id, text=caption, parse_mode="Markdown", reply_markup=reply_markup)
            else:
                if query.message.photo:
                    await query.message.delete()
                    await context.bot.send_message(chat_id=query.message.chat_id, text=caption, parse_mode="Markdown", reply_markup=reply_markup)
                else:
                    await query.edit_message_text(text=caption, parse_mode="Markdown", reply_markup=reply_markup)
        except BadRequest as e:
            logger.error(f"Carousel error: {e}")

# ─── Carousel Navigation (Stateless) ─────────────────────────────
async def handle_carousel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query

    # Anti-spam state machine check
    if context.user_data.get("user_state") == "processing":
        try:
            await query.answer("⏳ Processing your order. Please wait...", show_alert=True)
        except Exception: pass
        return

    await query.answer()

    # Enforce browsing state
    context.user_data["user_state"] = "browsing"

    if query.data == "nav_home":
        await start(update, context)
        return


    if "current_list" not in context.user_data:
        await start(update, context)
        return

    idx, total = context.user_data["current_idx"], len(context.user_data["current_list"])
    if query.data == "nav_next": context.user_data["current_idx"] = (idx + 1) % total
    elif query.data == "nav_prev": context.user_data["current_idx"] = (idx - 1) % total
    elif query.data.startswith("buyfast_"):
        context.user_data["buy_now"] = True
        await show_size_selection(query, context, query.data.split("buyfast_")[1])
        return
    elif query.data.startswith("buy_"):
        context.user_data["buy_now"] = False
        await show_size_selection(query, context, query.data.split("buy_")[1])
        return

    await render_product(query, context, edit_current=True)

# ─── Size Selection (Stateless) ──────────────────────────────────
async def show_size_selection(query, context: ContextTypes.DEFAULT_TYPE, product_id: str) -> None:
    shop_id = tenant_context.get_shop_id(None, context)
    product = db.get_product_by_id(product_id, shop_id)
    sizes = db.get_available_sizes(product_id, shop_id)
    context.user_data.update({"product": product, "product_id": product_id})

    keyboard = []
    row = []
    for i, stock in enumerate(sizes):
        qty = stock.get("quantity", 0)
        scarcity = ""
        if qty == 1:
            scarcity = " ⚠️ (1 left!)"
        elif qty <= 3:
            scarcity = f" (Only {qty} left)"

        btn_text = f"[{stock['size']}]{scarcity}"
        if len(set(s['price'] for s in sizes)) > 1:
            btn_text += f" - {stock['price']:,.0f}"

        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"size_{stock['size']}"))
        if len(row) == 2 or i == len(sizes) - 1: # Group into pairs for a cleaner design with labels
            keyboard.append(row)
            row = []

    keyboard.append([InlineKeyboardButton("🔙 Back to Product", callback_data="back_to_product")])

    is_buy_now = context.user_data.get("buy_now", False)
    flow_title = "⚡ Buy Now Selection" if is_buy_now else "🛒 Add to Cart Selection"
    text = f"✨ *{product['name']}* | {flow_title}\n\n👉 *Tap the option you want to purchase:*"

    if query.message.photo:
        await query.message.delete()
        await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

async def select_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "back_to_product":
        await render_product(query, context, edit_current=True)
        return

    if "product" not in context.user_data:
        await start(update, context)
        return

    size = query.data.replace("size_", "")
    product_id = context.user_data.get("product_id")
    product = context.user_data.get("product")
    shop_id = tenant_context.get_shop_id(update, context)
    stock = db.check_stock(product_id, size, shop_id)

    if not stock:
        keyboard = [[InlineKeyboardButton("🔙 Browse Other Sizes", callback_data="back_to_product")]]
        await safe_edit(query, "😔 Sorry, that size just sold out.", InlineKeyboardMarkup(keyboard))
        return

    cart_item = {
        "product_id": product_id, "product_name": product["name"],
        "size": size, "price": stock["price"],
        "stock_id": stock["id"], "stock_qty": stock["quantity"]
    }

    is_buy_now = context.user_data.get("buy_now", False)

    if is_buy_now:
        # Buy Now Flow: Skip cart, store this single item in cart and redirect immediately to checkout
        context.user_data["cart"] = [cart_item]

        keyboard = [
            [InlineKeyboardButton("⚡ Confirm & Checkout", callback_data="buy_now_checkout")],
            [InlineKeyboardButton("🔙 Back to Product", callback_data="back_to_product")]
        ]

        await safe_edit(
            query,
            f"⚡ *Option Selected!*\n\n"
            f"└ *Product:* {product['name']} (Size {size})\n"
            f"└ *Price:* {stock['price']:,.0f} ETB\n\n"
            f"Ready to complete your purchase? Tap below to finish order instantly:",
            InlineKeyboardMarkup(keyboard)
        )
    else:
        # Standard Cart Flow
        if "cart" not in context.user_data: context.user_data["cart"] = []
        context.user_data["cart"].append(cart_item)

        keyboard = [
            [InlineKeyboardButton("🛍️ Keep Browsing", callback_data="keep_browsing")],
            [InlineKeyboardButton("✅ Checkout Now", callback_data="checkout_now")]
        ]

        await safe_edit(
            query,
            f"🛒 *Added to Cart!*\n\n"
            f"└ {product['name']} (Size {size})\n"
            f"└ 💰 {stock['price']:,.0f} ETB\n\n"
            f"Your cart has {len(context.user_data['cart'])} item(s).",
            InlineKeyboardMarkup(keyboard)
        )

# ─── Cart View & Actions (Stateless) ─────────────────────────────
async def handle_cart_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "keep_browsing":
        await start(update, context)
    elif query.data == "clear_cart":
        context.user_data["cart"] = []
        await safe_edit(query, "🗑️ Your cart is empty.")
        await start(update, context)

async def show_cart(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    cart = context.user_data.get("cart", [])
    if not cart:
        await query.answer("Your cart is empty!", show_alert=True)
        await start(query, context) # Fallback to start
        return

    text = "🛒 *Your Cart*\n\n"
    total = 0
    for i, item in enumerate(cart):
        text += f"{i+1}. {item['product_name']} (Size {item['size']})\n    └ {item['price']:,.0f} ETB\n\n"
        total += item['price']

    text += f"💳 *Total: {total:,.0f} ETB*"

    keyboard = [
        [InlineKeyboardButton("✅ Checkout Now", callback_data="checkout_now")],
        [InlineKeyboardButton("🛍️ Keep Browsing", callback_data="keep_browsing")],
        [InlineKeyboardButton("🗑️ Clear Cart", callback_data="clear_cart")]
    ]

    if query.message.photo:
        await query.message.delete()
        await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))

# ─── Checkout Flow (Stateful) ────────────────────────────────────
async def start_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    update_activity(context)
    query = update.callback_query
    await query.answer()

    if not context.user_data.get("cart"):
        await query.answer("Your cart is empty!", show_alert=True)
        return ConversationHandler.END
    # Transition to checking_out state
    context.user_data["user_state"] = "checking_out"

    await typing_illusion(update, context)

    shop_id = tenant_context.get_shop_id(update, context)
    profile = db.get_customer_profile(query.from_user.id, shop_id)
    if profile:
        context.user_data["saved_profile"] = profile
        text = (
            f"⚡ *Fast Checkout*\n\n"
            f"I remember you! Use these details?\n\n"
            f"👤 {profile['customer_name']}\n"
            f"📱 {profile['customer_phone']}\n"
            f"📍 {profile['delivery_location']}\n"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Yes, use these", callback_data="use_profile")],
            [InlineKeyboardButton("✏️ No, enter new", callback_data="new_profile")]
        ]
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
        return CONFIRM_PROFILE
    else:
        await safe_edit(query, "👤 *What is your full name?*")
        return ENTER_NAME

async def confirm_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    if query.data == "use_profile":
        context.user_data.update(context.user_data["saved_profile"])
        return await show_final_confirmation(query, context)
    else:
        await safe_edit(query, "👤 *What is your full name?*")
        return ENTER_NAME

async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    update_activity(context)
    name = update.message.text.strip()
    if len(name) < 2: return ENTER_NAME
    context.user_data["customer_name"] = name
    await typing_illusion(update, context)
    await update.message.reply_text(f"📱 *Phone number?*\n_(e.g. 0912345678)_", parse_mode="Markdown")
    return ENTER_PHONE

async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    update_activity(context)
    phone = update.message.text.strip().replace(" ", "").replace("-", "")
    if len(phone.replace("+251", "0")) != 10:
        await update.message.reply_text("⚠️ Phone must be 10 digits. Try again.")
        return ENTER_PHONE
    context.user_data["customer_phone"] = phone
    await typing_illusion(update, context)
    await update.message.reply_text("📍 *Delivery location?*\n_(e.g. Bole, Addis Ababa)_", parse_mode="Markdown")
    return ENTER_LOCATION

async def enter_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    update_activity(context)
    context.user_data["delivery_location"] = update.message.text.strip()
    await typing_illusion(update, context)
    class DummyQuery:
        message = update.message
        async def edit_message_text(self, *args, **kwargs): return await update.message.reply_text(*args, **kwargs)
    return await show_final_confirmation(DummyQuery(), context)

async def show_final_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data
    cart = data.get("cart", [])
    shop_id = tenant_context.get_shop_id(None, context)

    # Load dynamic boutique identity details
    shop_details = db.get_shop_details(shop_id)
    emoji = shop_details.get("theme_emoji", "💎")
    shop_name = shop_details.get("name", "YourCloser")
    delivery_text = shop_details.get("delivery_text")

    text = f"{emoji} *{shop_name} — Confirm Order*\n\n"
    total = 0
    for item in cart:
        text += f"📦 {item['product_name']} (Size {item['size']}) - {item['price']:,.0f} ETB\n"
        total += item['price']

    text += f"\n💳 *Total: {total:,.0f} ETB*\n"
    if delivery_text:
        text += f"🚚 *Delivery:* {delivery_text}\n"

    text += f"\n👤 {data['customer_name']}\n📱 {data['customer_phone']}\n📍 {data['delivery_location']}\n\nIs everything correct?"

    keyboard = [
        [InlineKeyboardButton("✅ Confirm Entire Order", callback_data="confirm_yes")],
        [InlineKeyboardButton("✏️ Edit Details", callback_data="edit_details")],
        [InlineKeyboardButton("❌ Cancel", callback_data="confirm_no")]
    ]
    await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        context.user_data["user_state"] = "idle"
        await safe_edit(query, "❌ Order cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    if query.data == "edit_details":
        await safe_edit(query, "👤 *Let's re-enter your details.*\n\nWhat is your full name?")
        return ENTER_NAME

    user = update.effective_user

    # SESSION LOCK: Prevent duplicate submission (10-second checkout lock)
    if not acquire_order_lock(user.id):
        await safe_edit(query, "⏳ *Your order is already being processed. Please wait...*", None)
        return ConversationHandler.END

    try:
        # STATE MACHINE: Mark as processing — all other handlers will reject input
        context.user_data["user_state"] = "processing"

        # ANTI-SPAM: Immediately remove buttons so user cannot double-tap
        await safe_edit(query, "⏳ *Processing your order...*", None)

        data = context.user_data
        cart = data.get("cart", [])
        shop_id = tenant_context.get_shop_id(update, context)

        out_of_stock = []
        # FINAL ATOMIC-STYLE CHECK
        for item in cart:
            stock = db.check_stock(item["product_id"], item["size"], shop_id)
            if not stock or stock["quantity"] <= 0: out_of_stock.append(item["product_name"])

        if out_of_stock:
            context.user_data["user_state"] = "browsing"
            await safe_edit(query, f"⚠️ Oops! {', '.join(out_of_stock)} just sold out while you were checking out.\nPlease clear your cart and try again.")
            return ConversationHandler.END

        total = 0
        success_count = 0
        for i, item in enumerate(cart):
            # Atomic decrement — if returns None, item sold out between checks
            decrement_result = db.decrement_stock_atomic(item["stock_id"], shop_id)
            if not decrement_result:
                logger.warning(f"Stock conflict (atomic) for {item['product_name']} size {item['size']}")
                continue

            order = db.create_order(
                product_id=item["product_id"], product_name=item["product_name"], size=item["size"], price=item["price"],
                customer_name=data["customer_name"], customer_phone=data["customer_phone"], delivery_location=data["delivery_location"],
                telegram_user_id=user.id, telegram_username=user.username,
                shop_id=shop_id,
            )

            remaining = decrement_result.get("quantity", "?")
            logger.info(f"ORDER PLACED: {user.id} bought {item['product_name']} size {item['size']} — Stock remaining: {remaining}")

            total += item["price"]
            success_count += 1
            await notify_owner_order(context, data, user, order, item, i+1, len(cart))

        if success_count > 0:
            await safe_edit(query, f"🎉 *Order Confirmed!*\n\n{success_count} item(s) for {total:,.0f} ETB.\nThe boutique will contact you shortly! 🙏")
        else:
            await safe_edit(query, "❌ Your order could not be completed due to stock conflicts.")
        context.user_data.pop("cart", None)
        context.user_data["user_state"] = "idle"
        return ConversationHandler.END
    finally:
        # ALWAYS release the lock — even on error
        release_order_lock(user.id)

async def notify_owner_order(context: ContextTypes.DEFAULT_TYPE, data: dict, user, order: dict, item: dict, idx: int, total_items: int) -> None:
    if not settings.TELEGRAM_OWNER_CHAT_ID: return
    keyboard = [[InlineKeyboardButton("✅ Confirm", callback_data=f"owner_confirm_{order['id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"owner_reject_{order['id']}")]]
    text = (f"🚨 *NEW ORDER ({idx}/{total_items})*\n\n"
            f"📦 {item['product_name']} (Size {item['size']})\n💰 {item['price']:,.0f} ETB\n\n"
            f"👤 {data['customer_name']}\n📱 {data['customer_phone']}\n📍 {data['delivery_location']}\n"
            f"🆔 @{user.username or user.id}")
    await context.bot.send_message(chat_id=settings.TELEGRAM_OWNER_CHAT_ID, text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def owner_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != settings.TELEGRAM_OWNER_CHAT_ID: return await query.answer("⚠️ Owner only.", show_alert=True)
    parts = query.data.split("_")
    action, order_id = parts[1], "_".join(parts[2:])
    shop_id = tenant_context.get_shop_id(update, context)

    if action == "confirm":
        db.update_order_status(order_id, "confirmed", shop_id)
        text = query.message.text + "\n\n✅ *CONFIRMED*"
        keyboard = [[
            InlineKeyboardButton("🚚 Mark On Way", callback_data=f"owner_onway_{order_id}"),
            InlineKeyboardButton("📦 Mark Delivered", callback_data=f"owner_delivered_{order_id}")
        ], [InlineKeyboardButton("❌ Cancel Order", callback_data=f"owner_reject_{order_id}")]]
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
    elif action == "reject":
        db.update_order_status(order_id, "cancelled", shop_id)
        base_text = query.message.text.split("\n\n✅")[0].split("\n\n🚚")[0]
        await safe_edit(query, base_text + "\n\n❌ *CANCELLED*")
    elif action == "onway":
        db.update_order_status(order_id, "on_way", shop_id)
        base_text = query.message.text.split("\n\n✅")[0].split("\n\n🚚")[0]
        text = base_text + "\n\n🚚 *ON WAY*"
        keyboard = [[InlineKeyboardButton("📦 Mark Delivered", callback_data=f"owner_delivered_{order_id}")]]
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
    elif action == "delivered":
        db.update_order_status(order_id, "delivered", shop_id)
        base_text = query.message.text.split("\n\n✅")[0].split("\n\n🚚")[0]
        await safe_edit(query, base_text + "\n\n📦 *DELIVERED*")


async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Owner-only admin command center."""
    if str(update.effective_user.id) != settings.TELEGRAM_OWNER_CHAT_ID:
        await update.message.reply_text("⚠️ Owner only.")
        return ConversationHandler.END

    shop_id = tenant_context.get_shop_id(update, context)
    stats = db.get_stats(shop_id)
    shop_details = db.get_shop_details(shop_id)
    shop_name = shop_details.get("name", "YourCloser")
    emoji = shop_details.get("theme_emoji", "💎")

    text = (
        f"{emoji} *{shop_name} Admin Panel*\n\n"
        f"📦 *Total Orders:* {stats['total_orders']}\n"
        f"⏳ *Pending:* {stats['pending']}\n"
        f"✅ *Confirmed:* {stats['confirmed']}\n"
        f"💰 *Revenue:* {stats['revenue']:,.0f} ETB"
    )
    keyboard = [
        [InlineKeyboardButton("➕ Add Product", callback_data="admin_add_product")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_HOME


async def admin_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle admin panel button actions."""
    query = update.callback_query
    await query.answer()
    if str(query.from_user.id) != settings.TELEGRAM_OWNER_CHAT_ID:
        await query.answer("⚠️ Owner only.", show_alert=True)
        return ConversationHandler.END

    if query.data == "admin_close":
        await safe_edit(query, "Panel closed.")
        return ConversationHandler.END
    if query.data == "admin_broadcast":
        await safe_edit(query, "📢 *Broadcast Mode*\n\nType your message (or 'cancel'):")
        return ADMIN_BROADCAST
    if query.data == "admin_add_product":
        await safe_edit(query, "📸 *Add Product*\n\nSend a clear, high-quality photo of the product:")
        return ADMIN_ADD_PHOTO

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message.text
    if msg.lower().strip() == 'cancel':
        await update.message.reply_text("Cancelled.")
        return ConversationHandler.END

    shop_id = tenant_context.get_shop_id(update, context)
    customers = db.get_all_customers(shop_id)
    if not customers:
        await update.message.reply_text("No customers yet.")
        return ConversationHandler.END

    await update.message.reply_text(f"🚀 Sending to {len(customers)} customers in the background...")

    async def send_broadcast():
        success = 0
        for uid in customers:
            try:
                await context.bot.send_message(chat_id=uid, text=f"📢 *VIP Update:*\n\n{msg}", parse_mode="Markdown")
                success += 1
                await asyncio.sleep(0.05)  # Prevent Telegram rate limiting (max 30 msgs/sec)
            except Exception: pass

        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"✅ Broadcast complete! Delivered to {success}/{len(customers)} customers."
            )
        except Exception: pass

    # Run the broadcast in the background so it doesn't block the webhook
    asyncio.create_task(send_broadcast())

    return ConversationHandler.END

async def admin_add_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        await update.message.reply_text("⚠️ Please send a PHOTO (not a file or text).")
        return ADMIN_ADD_PHOTO
    file_id = update.message.photo[-1].file_id
    context.user_data["admin_new_prod"] = {"image_url": file_id}

    # Auto-Parsing from a forwarded channel post (photo + caption containing details)
    if update.message.caption:
        caption = update.message.caption.strip()
        parsed = parse_product_text(caption)

        # Clean description to remove category, size, price, qty lines if present
        desc_lines = []
        for line in caption.split("\n")[1:]:
            l = line.strip().lower()
            if any(l.startswith(prefix) for prefix in ["category", "sizes", "size", "price", "qty", "quantity", "💰", "🏷️", "📦"]):
                continue
            desc_lines.append(line)
        desc = "\n".join(desc_lines).strip()

        prod = context.user_data["admin_new_prod"]
        prod.update({
            "name": parsed["name"] or caption.split("\n")[0][:50],
            "desc": desc,
            "category": parsed["category"] or "Uncategorized",
            "sizes": parsed["sizes"] if parsed.get("sizes") else ["Standard"],
            "qty": parsed["qty"] if parsed.get("qty") else 10
        })

        if parsed.get("price", 0) > 0:
            prod["price"] = parsed["price"]
            confirm_text = (
                f"⚡ *Channel Post Auto-Parsed!* 📦\n\n"
                f"✨ *Name:* {prod['name']}\n"
                f"📝 *Desc:* {prod['desc']}\n"
                f"🏷️ *Category:* {prod['category']}\n"
                f"🏷️ *Options:* {', '.join(prod['sizes'])}\n"
                f"💰 *Price:* {prod['price']:,.0f} ETB\n"
                f"📦 *Quantity/Size:* {prod['qty']}\n\n"
                f"Ready to publish instantly?"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Publish Now", callback_data="admin_prod_publish")],
                [InlineKeyboardButton("❌ Cancel & Restart", callback_data="admin_prod_cancel")]
            ]
            await update.message.reply_photo(
                photo=prod["image_url"],
                caption=confirm_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return ADMIN_CONFIRM_PROD
        else:
            # Price is missing (e.g. flowers or custom boutique with no clear price field)
            await update.message.reply_text(
                f"💰 *Channel Post Detected!* 📦\n\n"
                f"I've extracted the photo and text, but I couldn't find the price.\n\n"
                f"👉 *Please type the price in ETB (e.g. 3500):*",
                parse_mode="Markdown"
            )
            return ADMIN_ADD_PRICE

    tip_text = (
        "✨ *Great photo!*\n\n"
        "What is the Product Name?\n"
        "_(e.g. Nike Dunk Low Panda)_\n\n"
        "💡 *WhatsApp-Style Onboarding:* You can also forward a post directly from your Telegram channel, or type all details in a single message now, and I will parse it automatically!\n"
        "Example:\n"
        "`Nike Dunk Low, Category: Shoes, Sizes: 40,41,42, Price: 6000, Qty: 3`"
    )
    await update.message.reply_text(tip_text, parse_mode="Markdown")
    return ADMIN_ADD_NAME

async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()

    # Try parsing WhatsApp-style input
    parsed = parse_product_text(text)
    if parsed.get("price", 0) > 0 and parsed.get("sizes"):
        # Successfully parsed single text block!
        prod = context.user_data["admin_new_prod"]
        prod.update({
            "name": parsed["name"] or text.split("\n")[0][:50],
            "desc": parsed["desc"],
            "category": parsed["category"],
            "sizes": parsed["sizes"],
            "price": parsed["price"],
            "qty": parsed["qty"]
        })

        confirm_text = (
            f"⚡ *WhatsApp-Style Parsing Success!*\n\n"
            f"✨ *Name:* {prod['name']}\n"
            f"📝 *Desc:* {prod['desc']}\n"
            f"🏷️ *Category:* {prod['category']}\n"
            f"🏷️ *Options:* {', '.join(prod['sizes'])}\n"
            f"💰 *Price:* {prod['price']:,.0f} ETB\n"
            f"📦 *Quantity/Size:* {prod['qty']}\n\n"
            f"Ready to publish?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Publish Now", callback_data="admin_prod_publish")],
            [InlineKeyboardButton("❌ Cancel & Restart", callback_data="admin_prod_cancel")]
        ]
        await update.message.reply_photo(
            photo=prod["image_url"],
            caption=confirm_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_CONFIRM_PROD

    # Standard wizard fallback
    context.user_data["admin_new_prod"]["name"] = text
    await update.message.reply_text("📝 *Short Description?*\n_(e.g. Premium quality, best seller)_", parse_mode="Markdown")
    return ADMIN_ADD_DESC

async def admin_add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_new_prod"]["desc"] = update.message.text.strip()
    keyboard = [
        [InlineKeyboardButton("👟 Shoes", callback_data="admincat_Shoes"), InlineKeyboardButton("👕 Hoodies", callback_data="admincat_Hoodies")],
        [InlineKeyboardButton("💻 Tech", callback_data="admincat_Tech"), InlineKeyboardButton("🧢 Accessories", callback_data="admincat_Accessories")]
    ]
    await update.message.reply_text("🏷️ *Which category?*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_ADD_CAT

async def admin_add_cat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    cat = query.data.replace("admincat_", "")
    context.user_data["admin_new_prod"]["category"] = cat
    await safe_edit(query, "🏷️ *Options/Variants*\n\nEnter all available options separated by commas:\n_(e.g. M, L, XL OR 128GB, 256GB)_")
    return ADMIN_ADD_SIZE

async def admin_add_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    sizes_str = update.message.text.strip()
    sizes = [s.strip() for s in sizes_str.split(",") if s.strip()]
    if not sizes:
        await update.message.reply_text("⚠️ Invalid format. Try: 40, 41, 42")
        return ADMIN_ADD_SIZE
    context.user_data["admin_new_prod"]["sizes"] = sizes
    await update.message.reply_text("💰 *Price*\n\nWhat is the price in ETB for these?\n_(e.g. 4500)_", parse_mode="Markdown")
    return ADMIN_ADD_PRICE

async def admin_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: price = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Please enter a number only.")
        return ADMIN_ADD_PRICE

    prod = context.user_data["admin_new_prod"]
    prod["price"] = price

    # If this was auto-parsed and we already have sizes and quantity, skip to confirmation!
    if prod.get("sizes") and prod.get("qty"):
        text = (
            f"📋 *Confirm New Product*\n\n"
            f"✨ *Name:* {prod['name']}\n"
            f"📝 *Desc:* {prod['desc']}\n"
            f"🏷️ *Category:* {prod['category']}\n"
            f"🏷️ *Options:* {', '.join(prod['sizes'])}\n"
            f"💰 *Price:* {prod['price']:,.0f} ETB\n"
            f"📦 *Quantity/Size:* {prod['qty']}\n\n"
            f"Ready to publish?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Publish Now", callback_data="admin_prod_publish")],
            [InlineKeyboardButton("❌ Cancel & Restart", callback_data="admin_prod_cancel")]
        ]
        await update.message.reply_photo(
            photo=prod["image_url"],
            caption=text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ADMIN_CONFIRM_PROD

    await update.message.reply_text("📦 *Quantity*\n\nHow many do you have in stock per size?\n_(e.g. 5)_", parse_mode="Markdown")
    return ADMIN_ADD_QTY

async def admin_add_qty(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: qty = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Please enter a whole number.")
        return ADMIN_ADD_QTY

    context.user_data["admin_new_prod"]["qty"] = qty
    prod = context.user_data["admin_new_prod"]

    text = (
        f"📋 *Confirm New Product*\n\n"
        f"✨ *Name:* {prod['name']}\n"
        f"📝 *Desc:* {prod['desc']}\n"
        f"🏷️ *Category:* {prod['category']}\n"
        f"🏷️ *Options:* {', '.join(prod['sizes'])}\n"
        f"💰 *Price:* {prod['price']:,.0f} ETB\n"
        f"📦 *Quantity/Size:* {qty}\n\n"
        f"Ready to publish?"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Publish Now", callback_data="admin_prod_publish")],
        [InlineKeyboardButton("❌ Cancel & Restart", callback_data="admin_prod_cancel")]
    ]

    await update.message.reply_photo(
        photo=prod["image_url"],
        caption=text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_CONFIRM_PROD

async def admin_confirm_prod(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "admin_prod_cancel":
        if query.message.photo:
            try:
                await query.message.delete()
            except Exception: pass
            await context.bot.send_message(chat_id=query.message.chat_id, text="❌ Product creation cancelled. Type /admin to start again.")
        else:
            await safe_edit(query, "❌ Product creation cancelled. Type /admin to start again.")
        context.user_data.pop("admin_new_prod", None)
        return ConversationHandler.END

    prod = context.user_data["admin_new_prod"]
    shop_id = tenant_context.get_shop_id(update, context)
    product_id = db.add_product(prod["name"], prod["desc"], prod["category"], prod["image_url"], shop_id)
    for s in prod["sizes"]:
        db.add_stock(product_id, s, prod["qty"], prod["price"], shop_id)

    text = f"🎉 *Product Added Successfully!*\n\n{prod['name']} is now live in the {prod['category']} store."
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Close Admin", callback_data="admin_close")]])

    if query.message.photo:
        try:
            await query.message.delete()
        except Exception: pass
        await context.bot.send_message(chat_id=query.message.chat_id, text=text, parse_mode="Markdown", reply_markup=markup)
    else:
        await safe_edit(query, text, markup)

    context.user_data.pop("admin_new_prod", None)
    return ConversationHandler.END

# ─── Boilerplate ─────────────────────────────────────────────────
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text("Cancelled. Type /start to begin.")
    return ConversationHandler.END

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Sorry 😅 I didn’t understand that.\n\n"
        "Please choose an option from the menu or type the product name you’re looking for."
    )
    await update.message.reply_text(text)

def build_bot_app() -> Application:
    persistence = PicklePersistence(filepath="yourcloser_data.pickle")
    app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).persistence(persistence).request(HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)).build()

    # 1. Global Stateless Handlers (Guaranteed to work regardless of container resets)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_home_menu, pattern=r"^(cat_.*|new_arrivals|view_cart|track_orders|discover_.*)$"))
    app.add_handler(CallbackQueryHandler(handle_carousel, pattern=r"^(nav_next|nav_prev|buy_.*|buyfast_.*|nav_home)$"))
    app.add_handler(CallbackQueryHandler(select_size, pattern=r"^(size_.*|back_to_product)$"))
    app.add_handler(CallbackQueryHandler(handle_cart_view, pattern=r"^(keep_browsing|clear_cart)$"))

    # 2. Search Conversation
    search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_search, pattern=r"^search_mode$")],
        states={SEARCH_PRODUCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search)]},
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        per_user=True, per_chat=True,
        conversation_timeout=3600
    )
    app.add_handler(search_conv)

    # 3. Checkout Conversation
    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(start_checkout, pattern=r"^(checkout_now|buy_now_checkout)$")],
        states={
            CONFIRM_PROFILE: [CallbackQueryHandler(confirm_profile)],
            ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
            ENTER_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_phone)],
            ENTER_LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_location)],
            CONFIRM_ORDER: [CallbackQueryHandler(confirm_order)],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        per_user=True, per_chat=True,
        conversation_timeout=3600
    )
    app.add_handler(checkout_conv)

    # 4. Admin Conversation
    admin_conv = ConversationHandler(
        entry_points=[CommandHandler("admin", admin_start)],
        states={
            ADMIN_HOME: [CallbackQueryHandler(admin_home)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast)],
            ADMIN_ADD_PHOTO: [MessageHandler(filters.PHOTO, admin_add_photo)],
            ADMIN_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_name)],
            ADMIN_ADD_DESC: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_desc)],
            ADMIN_ADD_CAT: [CallbackQueryHandler(admin_add_cat, pattern=r"^admincat_")],
            ADMIN_ADD_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_size)],
            ADMIN_ADD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_price)],
            ADMIN_ADD_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_qty)],
            ADMIN_CONFIRM_PROD: [CallbackQueryHandler(admin_confirm_prod, pattern=r"^admin_prod_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True, per_chat=True,
        conversation_timeout=3600
    )
    app.add_handler(admin_conv)

    app.add_handler(CallbackQueryHandler(owner_action, pattern=r"^owner_"))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, fallback))
    return app
