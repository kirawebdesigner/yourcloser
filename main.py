"""
YourCloser — FastAPI Server + Telegram Webhook
Entry point for the entire application.
"""
import logging
import uvicorn
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from telegram import Update

from config import settings
from handlers import build_bot_app

# ─── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ─── Bot Application (global) ────────────────────────────────────
bot_app = build_bot_app()

async def setup_commands(app_instance):
    from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
    
    await app_instance.bot.set_my_commands(
        [BotCommand("start", "Start browsing the boutique")],
        scope=BotCommandScopeDefault()
    )
    
    if settings.TELEGRAM_OWNER_CHAT_ID:
        try:
            await app_instance.bot.set_my_commands(
                [
                    BotCommand("start", "Start browsing the boutique"),
                    BotCommand("admin", "Open boutique command center"),
                    BotCommand("create_shop", "Create a new boutique")
                ],
                scope=BotCommandScopeChat(chat_id=settings.TELEGRAM_OWNER_CHAT_ID)
            )
        except Exception as e:
            logger.warning(f"Could not set admin commands: {e}")


async def abandoned_cart_recovery_loop(app):
    """
    Background loop that runs every 60 seconds.
    It checks app.user_data for users who:
    1. Have items in their cart.
    2. Have not had any activity in the last 30 minutes (1800 seconds).
    3. Have not been notified yet (recovery_notified == False).
    """
    import time
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    logger.info("⏰ Abandoned Cart Recovery loop started")
    while True:
        try:
            await asyncio.sleep(60) # check every minute
            now = time.time()
            # Iterate over a copy of the keys to avoid dictionary size change during iteration
            for user_id, udata in list(app.user_data.items()):
                cart = udata.get("cart")
                if not cart:
                    continue
                
                # Check inactivity
                last_activity = udata.get("last_activity")
                if not last_activity:
                    # Initialize last_activity if not present
                    udata["last_activity"] = now
                    continue
                    
                inactivity_seconds = now - last_activity
                # If they have been inactive for > 30 minutes (or 1800 seconds) and not notified
                if inactivity_seconds >= 1800 and not udata.get("recovery_notified", False):
                    # Flag them so we don't double-notify
                    udata["recovery_notified"] = True
                    
                    # Send friendly reminder!
                    try:
                        text = (
                            "👋 *Hey there!* We noticed you left some premium items in your cart:\n\n"
                        )
                        total = 0
                        for i, item in enumerate(cart):
                            text += f"▪️ *{item['product_name']}* (Size {item['size']}) — {item['price']:,.0f} ETB\n"
                            total += item['price']
                        
                        text += f"\n💰 *Total: {total:,.0f} ETB*\n\n"
                        text += "These high-demand items sell out fast! Would you like to complete your order now?"
                        
                        keyboard = [
                            [InlineKeyboardButton("✅ Checkout Now", callback_data="checkout_now")],
                            [InlineKeyboardButton("🛒 View Cart", callback_data="view_cart")],
                            [InlineKeyboardButton("🔙 Return to Store", callback_data="nav_home")]
                        ]
                        
                        await app.bot.send_message(
                            chat_id=user_id,
                            text=text,
                            parse_mode="Markdown",
                            reply_markup=InlineKeyboardMarkup(keyboard)
                        )
                        logger.info(f"✉️ Sent abandoned cart reminder to user {user_id}")
                        
                        if app.persistence:
                            await app.persistence.flush()
                    except Exception as send_err:
                        logger.error(f"Failed to send recovery message to {user_id}: {send_err}")
        except asyncio.CancelledError:
            logger.info("⏰ Abandoned Cart Recovery loop stopped")
            break
        except Exception as e:
            logger.error(f"Error in abandoned cart recovery loop: {e}")


# ─── Lifespan (startup/shutdown) ─────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup the Telegram bot."""
    settings.validate()
    await bot_app.initialize()
    await bot_app.start()
    await setup_commands(bot_app)

    # Start the Abandoned Cart Recovery background loop
    recovery_task = asyncio.create_task(abandoned_cart_recovery_loop(bot_app))

    # Set webhook if URL is configured, otherwise use polling
    if settings.WEBHOOK_URL:
        webhook_url = f"{settings.WEBHOOK_URL}/webhook"
        await bot_app.bot.set_webhook(url=webhook_url)
        logger.info(f"✅ Webhook set: {webhook_url}")
    else:
        logger.info("⚠️ No WEBHOOK_URL set — use /poll endpoint or run polling manually")

    logger.info("🚀 YourCloser is online!")
    yield

    # Cleanup
    recovery_task.cancel()
    try:
        await recovery_task
    except asyncio.CancelledError:
        pass
        
    await bot_app.stop()
    await bot_app.shutdown()
    logger.info("👋 YourCloser shutdown complete")


# ─── FastAPI App ──────────────────────────────────────────────────
app = FastAPI(
    title="YourCloser API",
    description="Telegram Sales Assistant for Boutique Stores",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Health Check ─────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "service": "YourCloser",
        "status": "online",
        "version": "1.0.0",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


# ─── Telegram Webhook ────────────────────────────────────────────
@app.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Receive Telegram updates via webhook.
    This is called by Telegram servers when a user sends a message.
    """
    try:
        data = await request.json()
        update = Update.de_json(data, bot_app.bot)
        await bot_app.process_update(update)
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return Response(status_code=200)  # Always return 200 to Telegram


# ─── Polling Mode (for local dev) ────────────────────────────────
@app.post("/poll")
async def start_polling():
    """
    Start polling mode for local development.
    Hit this endpoint once to start receiving updates via polling.
    Only use this for local development — use webhooks in production.
    """
    if settings.WEBHOOK_URL:
        return {"error": "Webhook is configured. Remove WEBHOOK_URL to use polling."}

    # Remove any existing webhook
    await bot_app.bot.delete_webhook()
    logger.info("🔄 Polling mode started")
    return {"status": "polling_started"}


# ─── Run ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not settings.WEBHOOK_URL:
        # Local dev: run with polling
        logger.info("🔧 Starting in POLLING mode (local dev)...")
        import asyncio

        async def run_polling():
            settings.validate()
            polling_app = build_bot_app()
            await polling_app.initialize()
            await polling_app.start()
            await setup_commands(polling_app)
            
            # Start the background task in polling mode
            recovery_task = asyncio.create_task(abandoned_cart_recovery_loop(polling_app))
            
            await polling_app.bot.delete_webhook()
            await polling_app.updater.start_polling(drop_pending_updates=True)
            logger.info("🚀 YourCloser is online! (Polling mode)")

            # Keep alive
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                recovery_task.cancel()
                try:
                    await recovery_task
                except asyncio.CancelledError:
                    pass
                await polling_app.updater.stop()
                await polling_app.stop()
                await polling_app.shutdown()

        asyncio.run(run_polling())
    else:
        # Production: run FastAPI with webhook
        uvicorn.run(
            "main:app",
            host=settings.HOST,
            port=settings.PORT,
            reload=False,
        )
