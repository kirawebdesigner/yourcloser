"""
YourCloser — Tenant Context Guard Layer
Single source of truth for multi-tenant shop_id extraction.
Every handler MUST call get_shop_id() — never trust user_data alone.
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def get_shop_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """
    Extracts the shop_id dynamically using a strict priority chain:
      1. /start deep link payload (highest trust)
      2. context.args from command messages
      3. Cached session value from user_data
      4. Fallback to "default" with WARNING log

    RULE: Every DB function receives this value explicitly.
    """
    # Safe check if context or user_data is missing
    if context is None or context.user_data is None:
        logger.warning("Tenant guard: context/user_data is None — returning 'default'")
        return "default"

    # 1. Deep link /start command (highest priority — first contact with shop)
    if update and update.message and update.message.text:
        text = update.message.text.strip()
        if text.startswith("/start "):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                arg = parts[1].strip()
                if arg:
                    context.user_data["shop_id"] = arg
                    logger.info(
                        f"Tenant: set shop_id='{arg}' from /start deep link "
                        f"(user={update.effective_user.id})"
                    )
                    return arg

    # 2. context.args (command messages like /start with args parsed by PTB)
    if update and update.message and context.args:
        arg = context.args[0].strip()
        if arg:
            context.user_data["shop_id"] = arg
            logger.info(
                f"Tenant: set shop_id='{arg}' from context.args "
                f"(user={update.effective_user.id})"
            )
            return arg

    # 3. Cached session value (set during a previous /start in this session)
    shop_id = context.user_data.get("shop_id")
    if shop_id:
        return shop_id

    # 4. Fallback — log a warning so we can trace multi-tenant leakage
    logger.warning(
        f"Tenant guard: no shop_id found for user "
        f"{update.effective_user.id if update and update.effective_user else '?'} "
        f"— falling back to 'default'"
    )
    context.user_data["shop_id"] = "default"
    return "default"
