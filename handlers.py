"""
YourCloser — Telegram Bot Handlers
Stateless Architecture for Serverless/Scale-to-Zero Deployment
"""
import logging
import asyncio
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

logger = logging.getLogger(__name__)

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
    if "cart" not in context.user_data: context.user_data["cart"] = []
        
    categories = db.get_categories()
    keyboard = []
    
    row = []
    for cat in categories:
        emoji = get_emoji_for_category(cat)
        row.append(InlineKeyboardButton(f"{emoji} {cat}", callback_data=f"cat_{cat}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)
        
    keyboard.append([InlineKeyboardButton("✨ New Arrivals", callback_data="new_arrivals")])
    keyboard.append([
        InlineKeyboardButton("🔍 Search", callback_data="search_mode"),
        InlineKeyboardButton("📦 Track Orders", callback_data="track_orders")
    ])
    
    if context.user_data.get("cart"):
        keyboard.append([InlineKeyboardButton(f"🛒 View Cart ({len(context.user_data['cart'])} items)", callback_data="view_cart")])

    text = (
        "💎 *Welcome to YourCloser!*\n\n"
        "Your premium 24/7 boutique assistant.\n\n"
        "Tap a category below to start browsing our catalog:"
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
    await query.answer()
    data = query.data
    
    if data == "track_orders":
        orders = db.get_user_orders(query.from_user.id)
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
        products = db.get_products_by_category(cat)
        title = f"{get_emoji_for_category(cat)} *{cat} Collection*"
    elif data == "new_arrivals":
        products = db.get_new_arrivals(5)
        title = "✨ *New Arrivals*"
        
    if not products:
        await query.answer("Nothing here yet!", show_alert=True)
        return
        
    context.user_data.update({"current_list": products, "current_idx": 0, "list_title": title})
    await render_product(query, context, edit_current=True)

# ─── Search Mode (Stateful) ──────────────────────────────────────
async def start_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await safe_edit(query, "🔍 *What are you looking for?*\n\n_Type the name of the product..._")
    return SEARCH_PRODUCT

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    q = update.message.text.strip()
    if len(q) < 2: return SEARCH_PRODUCT
        
    products = db.search_products(q)
    if not products:
        await update.message.reply_text(f"❌ Nothing found for \"{q}\". Try another keyword.")
        return SEARCH_PRODUCT
        
    context.user_data.update({"current_list": products, "current_idx": 0, "list_title": f"🔍 Search: {q}"})
    await render_product(update, context, edit_current=False)
    return ConversationHandler.END

# ─── Beautiful Product Carousel (Stateless) ──────────────────────
async def render_product(update_or_query, context: ContextTypes.DEFAULT_TYPE, edit_current: bool) -> None:
    if "current_list" not in context.user_data or not context.user_data["current_list"]:
        # Safety catch if container restarted and memory was lost
        if isinstance(update_or_query, Update) and update_or_query.callback_query:
            await start(update_or_query, context)
        return

    idx = context.user_data["current_idx"]
    products = context.user_data["current_list"]
    product = products[idx]
    
    sizes = db.get_available_sizes(product["id"])
    
    caption = f"📍 {context.user_data['list_title']}  ({idx + 1}/{len(products)})\n\n"
    caption += f"✨ *{product['name']}*\n"
    
    if product.get('description'): 
        caption += f"_{product['description']}_\n"
    
    caption += "\n"
    if sizes:
        prices = [s["price"] for s in sizes]
        price_display = f"{min(prices):,.0f} ETB" if min(prices) == max(prices) else f"{min(prices):,.0f} - {max(prices):,.0f} ETB"
        caption += f"💰 *Price:*  {price_display}\n"
        caption += f"🏷️ *Options:*  {', '.join([s['size'] for s in sizes])}\n"
    else:
        caption += f"🚫 *Currently Out of Stock*\n"
        
    keyboard = []
    if sizes: keyboard.append([InlineKeyboardButton("🛒 Select Option to Buy", callback_data=f"buy_{product['id']}")])
        
    nav_row = []
    if len(products) > 1:
        nav_row.extend([InlineKeyboardButton("⬅️", callback_data="nav_prev"), InlineKeyboardButton("➡️", callback_data="nav_next")])
    if nav_row: keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="nav_home")])
    
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
    await query.answer()
    
    if query.data == "nav_home": 
        await start(update, context)
        return
        
    if "current_list" not in context.user_data:
        await start(update, context)
        return

    idx, total = context.user_data["current_idx"], len(context.user_data["current_list"])
    if query.data == "nav_next": context.user_data["current_idx"] = (idx + 1) % total
    elif query.data == "nav_prev": context.user_data["current_idx"] = (idx - 1) % total
    elif query.data.startswith("buy_"): 
        await show_size_selection(query, context, query.data.split("_")[1])
        return
        
    await render_product(query, context, edit_current=True)

# ─── Size Selection (Stateless) ──────────────────────────────────
async def show_size_selection(query, context: ContextTypes.DEFAULT_TYPE, product_id: str) -> None:
    product = db.get_product_by_id(product_id)
    sizes = db.get_available_sizes(product_id)
    context.user_data.update({"product": product, "product_id": product_id})
    
    keyboard = []
    row = []
    for i, stock in enumerate(sizes):
        btn_text = f"[{stock['size']}]" + (f" - {stock['price']:,.0f}" if len(set(s['price'] for s in sizes)) > 1 else "")
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"size_{stock['size']}"))
        if len(row) == 3 or i == len(sizes) - 1:
            keyboard.append(row)
            row = []
            
    keyboard.append([InlineKeyboardButton("🔙 Back to Product", callback_data="back_to_product")])
    text = f"✨ *{product['name']}*\n\n👉 *Tap the option you want to add to your cart:*"
    
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
    stock = db.check_stock(product_id, size)
    
    if not stock:
        keyboard = [[InlineKeyboardButton("🔙 Browse Other Sizes", callback_data="back_to_product")]]
        await safe_edit(query, "😔 Sorry, that size just sold out.", InlineKeyboardMarkup(keyboard))
        return
        
    cart_item = {
        "product_id": product_id, "product_name": product["name"],
        "size": size, "price": stock["price"],
        "stock_id": stock["id"], "stock_qty": stock["quantity"]
    }
    
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
    query = update.callback_query
    await query.answer()
    
    if not context.user_data.get("cart"):
        await query.answer("Your cart is empty!", show_alert=True)
        return ConversationHandler.END

    profile = db.get_customer_profile(query.from_user.id)
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
    name = update.message.text.strip()
    if len(name) < 2: return ENTER_NAME
    context.user_data["customer_name"] = name
    await update.message.reply_text(f"📱 *Phone number?*\n_(e.g. 0912345678)_", parse_mode="Markdown")
    return ENTER_PHONE

async def enter_phone(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    phone = update.message.text.strip().replace(" ", "").replace("-", "")
    if len(phone.replace("+251", "0")) != 10:
        await update.message.reply_text("⚠️ Phone must be 10 digits. Try again.")
        return ENTER_PHONE
    context.user_data["customer_phone"] = phone
    await update.message.reply_text("📍 *Delivery location?*\n_(e.g. Bole, Addis Ababa)_", parse_mode="Markdown")
    return ENTER_LOCATION

async def enter_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["delivery_location"] = update.message.text.strip()
    class DummyQuery:
        message = update.message
        async def edit_message_text(self, *args, **kwargs): return await update.message.reply_text(*args, **kwargs)
    return await show_final_confirmation(DummyQuery(), context)

async def show_final_confirmation(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    data = context.user_data
    cart = data.get("cart", [])
    
    text = f"📋 *Confirm Order*\n\n"
    total = 0
    for item in cart:
        text += f"📦 {item['product_name']} (Size {item['size']}) - {item['price']:,.0f} ETB\n"
        total += item['price']
        
    text += f"\n💳 *Total: {total:,.0f} ETB*\n\n"
    text += f"👤 {data['customer_name']}\n📱 {data['customer_phone']}\n📍 {data['delivery_location']}\n\nIs everything correct?"
    
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
        await safe_edit(query, "❌ Order cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
        
    if query.data == "edit_details":
        await safe_edit(query, "👤 *Let's re-enter your details.*\n\nWhat is your full name?")
        return ENTER_NAME
        
    # ANTI-SPAM / IDEMPOTENCY: Immediately remove buttons so user cannot double-tap while processing
    await safe_edit(query, "⏳ *Processing your order...*", None)
    
    data = context.user_data
    user = update.effective_user
    cart = data.get("cart", [])
    
    out_of_stock = []
    # FINAL ATOMIC-STYLE CHECK
    for item in cart:
        stock = db.check_stock(item["product_id"], item["size"])
        if not stock or stock["quantity"] <= 0: out_of_stock.append(item["product_name"])
            
    if out_of_stock:
        await safe_edit(query, f"⚠️ Oops! {', '.join(out_of_stock)} just sold out while you were checking out.\nPlease clear your cart and try again.")
        return ConversationHandler.END

    total = 0
    success_count = 0
    for i, item in enumerate(cart):
        stock = db.check_stock(item["product_id"], item["size"])
        if not stock or stock["quantity"] <= 0:
            logger.warning(f"Stock conflict during creation for {item['product_name']}")
            continue # Skip this item if it sold out in the microsecond between checks
            
        order = db.create_order(
            product_id=item["product_id"], product_name=item["product_name"], size=item["size"], price=item["price"],
            customer_name=data["customer_name"], customer_phone=data["customer_phone"], delivery_location=data["delivery_location"],
            telegram_user_id=user.id, telegram_username=user.username,
        )
        
        # Decrement stock and log
        db.decrement_stock(item["stock_id"], stock["quantity"])
        logger.info(f"ORDER PLACED: {user.id} bought {item['product_name']} - Stock remaining: {stock['quantity'] - 1}")
        
        total += item["price"]
        success_count += 1
        await notify_owner_order(context, data, user, order, item, i+1, len(cart))
    
    if success_count > 0:
        await safe_edit(query, f"🎉 *Order Confirmed!*\n\n{success_count} item(s) for {total:,.0f} ETB.\nThe boutique will contact you shortly! 🙏")
    else:
        await safe_edit(query, "❌ Your order could not be completed due to stock conflicts.")
    context.user_data.pop("cart", None)
    return ConversationHandler.END

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
    
    if action == "confirm":
        db.update_order_status(order_id, "confirmed")
        text = query.message.text + "\n\n✅ *CONFIRMED*"
        keyboard = [[
            InlineKeyboardButton("🚚 Mark On Way", callback_data=f"owner_onway_{order_id}"),
            InlineKeyboardButton("📦 Mark Delivered", callback_data=f"owner_delivered_{order_id}")
        ], [InlineKeyboardButton("❌ Cancel Order", callback_data=f"owner_reject_{order_id}")]]
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
    elif action == "reject":
        db.update_order_status(order_id, "cancelled")
        base_text = query.message.text.split("\n\n✅")[0].split("\n\n🚚")[0]
        await safe_edit(query, base_text + "\n\n❌ *CANCELLED*")
    elif action == "onway":
        db.update_order_status(order_id, "on_way")
        base_text = query.message.text.split("\n\n✅")[0].split("\n\n🚚")[0]
        text = base_text + "\n\n🚚 *ON WAY*"
        keyboard = [[InlineKeyboardButton("📦 Mark Delivered", callback_data=f"owner_delivered_{order_id}")]]
        await safe_edit(query, text, InlineKeyboardMarkup(keyboard))
    elif action == "delivered":
        db.update_order_status(order_id, "delivered")
        base_text = query.message.text.split("\n\n✅")[0].split("\n\n🚚")[0]
        await safe_edit(query, base_text + "\n\n📦 *DELIVERED*")

# ─── Admin Dashboard & Seller Onboarding ─────────────────────────
async def admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if str(update.message.from_user.id) != settings.TELEGRAM_OWNER_CHAT_ID:
        await update.message.reply_text("⛔ Owner only.")
        return ConversationHandler.END
        
    stats = db.get_stats()
    text = (
        f"👑 *Boutique Command Center*\n\n"
        f"📈 *Revenue:* {stats['revenue']:,.0f} ETB\n"
        f"📦 *Total Orders:* {stats['total_orders']} ({stats['pending']} pending)\n\n"
        f"What do you want to do?"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Add New Product", callback_data="admin_add_product")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")],
        [InlineKeyboardButton("❌ Close Panel", callback_data="admin_close")]
    ]
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_HOME

async def admin_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
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
        
    customers = db.get_all_customers()
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
    await update.message.reply_text("✨ *Great photo!*\n\nWhat is the Product Name?\n_(e.g. Nike Dunk Low Panda)_", parse_mode="Markdown")
    return ADMIN_ADD_NAME

async def admin_add_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["admin_new_prod"]["name"] = update.message.text.strip()
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
    context.user_data["admin_new_prod"]["price"] = price
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
    product_id = db.add_product(prod["name"], prod["desc"], prod["category"], prod["image_url"])
    for s in prod["sizes"]:
        db.add_stock(product_id, s, prod["qty"], prod["price"])
        
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
    app.add_handler(CallbackQueryHandler(handle_home_menu, pattern=r"^(cat_.*|new_arrivals|view_cart|track_orders)$"))
    app.add_handler(CallbackQueryHandler(handle_carousel, pattern=r"^(nav_next|nav_prev|buy_.*|nav_home)$"))
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
        entry_points=[CallbackQueryHandler(start_checkout, pattern=r"^checkout_now$")],
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
