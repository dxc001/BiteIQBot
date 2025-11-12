import logging
import os
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.helpers import escape_markdown

from config import TELEGRAM_BOT_TOKEN
from database import SupabaseDB
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler

_logger = logging.getLogger(__name__)


def _md(text: Any) -> str:
    risky = ["\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]
    safe = escape_markdown(str(text), version=2)
    for char in risky:
        safe = safe.replace(char, f"\\{char}")
    return safe


class TelegramBot:
    def __init__(self, db: SupabaseDB, openai_handler: OpenAIHandler, stripe_handler: StripeHandler):
        self.db = db
        self.openai_handler = openai_handler
        self.stripe_handler = stripe_handler
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self._register_handlers()

    async def initialize(self):
        """Initialize Telegram bot and set webhook URL."""
        base_url = os.getenv("RENDER_EXTERNAL_URL", "https://biteiqbot-docker.onrender.com").rstrip("/")
        webhook_url = f"{base_url}/webhook"

        try:
            await self.application.bot.delete_webhook()
            await self.application.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            _logger.info(f"✅ Telegram webhook set to: {webhook_url}")
        except Exception as exc:
            _logger.warning(f"⚠️ Failed to set Telegram webhook: {exc}")

        await self.application.initialize()
        await self.application.start()
        _logger.info("🤖 Telegram bot initialized and ready for webhooks.")

    # --- Handlers ---
    def _register_handlers(self):
        self.application.add_handler(CommandHandler("start", self._start))
        self.application.add_handler(CommandHandler("menu", self._menu))

    async def _send_text(
        self, update: Update, text: str, parse_mode: Optional[str] = None, reply_markup: Optional[InlineKeyboardMarkup] = None
    ):
        chat = update.effective_chat
        if chat:
            await chat.send_message(text=text, parse_mode=parse_mode, reply_markup=reply_markup)

    async def _start(self, update: Update, _: ContextTypes.DEFAULT_TYPE):
        _logger.info(f"👤 Received /start from {update.effective_user.id}")
        await self._send_text(update, "👋 Welcome to BiteIQBot! The webhook is working ✅")

    async def _menu(self, update: Update, _: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("💳 Subscribe", callback_data="subscribe")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_text(update, "📋 Menu options:", reply_markup=reply_markup)


