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

_MD_RISKY = ["\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]


def _md(text: Any) -> str:
    safe = escape_markdown(str(text), version=2)
    for char in _MD_RISKY:
        safe = safe.replace(char, f"\\{char}")
    return safe


class TelegramBot:
    def __init__(self, db: SupabaseDB, openai_handler: OpenAIHandler, stripe_handler: StripeHandler):
        self.db = db
        self.openai_handler = openai_handler
        self.stripe_handler = stripe_handler
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self._register_handlers()

    async def initialize(self) -> None:
        """Initialize Telegram bot, enforce webhook to Render URL, and start dispatcher."""
        await self.application.initialize()

        base_url = os.getenv("RENDER_EXTERNAL_URL", "https://biteiqbot-docker.onrender.com").rstrip("/")
        webhook_url = f"{base_url}/webhook"

        try:
            # Remove old webhooks
            await self.application.bot.delete_webhook()
            await self.application.bot.set_webhook(url=webhook_url, drop_pending_updates=True)
            _logger.info(f"✅ Telegram webhook set to: {webhook_url}")
        except Exception as exc:
            _logger.warning(f"⚠️ Failed to set Telegram webhook: {exc}")

        # Start the dispatcher
        await self.application.start()
        await self.application.updater.start_polling()  # ensures handlers respond to webhook updates
        _logger.info("🤖 Telegram bot fully initialized and ready.")

    async def process_update_json(self, data: Dict[str, Any]) -> None:
        """Convert raw JSON into Telegram Update and process it."""
        update = Update.de_json(data, self.application.bot)
        await self.application.process_update(update)

    def _register_handlers(self) -> None:
        """Register all command and message handlers."""
        self.application.add_handler(CommandHandler("start", self._start))
        self.application.add_handler(CommandHandler("menu", self._menu))
        self.application.add_handler(CommandHandler("help", self._help))
        self.application.add_handler(CommandHandler("subscribe", self._subscribe))
        self.application.add_handler(CommandHandler("tomorrow", self._tomorrow))
        self.application.add_handler(CallbackQueryHandler(self._button_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))

    async def _send_text(
        self,
        update: Update,
        text: str,
        *,
        parse_mode: Optional[str] = None,
        reply_markup: Optional[InlineKeyboardMarkup] = None,
    ) -> None:
        """Utility method to send text messages safely."""
        chat = update.effective_chat
        try:
            if chat:
                await chat.send_message(text=text, parse_mode=parse_mode, reply_markup=reply_markup)
            elif update.callback_query and update.callback_query.message:
                await update.callback_query.message.reply_text(
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup,
                )
            _logger.info(f"📤 Sent message to user {chat.id if chat else 'unknown'}")
        except Exception as e:
            _logger.error(f"❌ Failed to send message: {e}")

    # -------------------- Command Handlers --------------------

    async def _start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        _logger.info(f"👤 Received /start from user {update.effective_user.id}")
        user = update.effective_user
        self.db.get_or_create_user(user.id, user.username)
        welcome = (
            "👋 *Welcome to BiteIQBot — your smart nutrition coach!* 🥗\n\n"
            "Send your profile details in 8 parts (comma or newline separated):\n"
            "1. Name\n2. Age\n3. Gender (M/F)\n4. Height (cm)\n5. Weight (kg)\n"
            "6. Activity (low/medium/high)\n7. Dietary preferences\n8. Goal weight (kg)"
        )
        await self._send_text(update, welcome, parse_mode="MarkdownV2")

    async def _menu(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        keyboard = [
            [InlineKeyboardButton("📅 Tomorrow Plan", callback_data="tomorrow_plan")],
            [InlineKeyboardButton("💳 Subscribe", callback_data="subscribe")],
            [InlineKeyboardButton("❓ Help", callback_data="help")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_text(
            update,
            "🍽️ *BiteIQ Menu*\nChoose an option:",
            parse_mode="MarkdownV2",
            reply_markup=reply_markup,
        )

    async def _help(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        help_text = (
            "ℹ️ *Commands*\n"
            "/start – restart setup\n/menu – show menu\n/tomorrow – get tomorrow's plan\n"
            "/subscribe – manage subscription"
        )
        await self._send_text(update, help_text, parse_mode="MarkdownV2")

    async def _subscribe(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        try:
            checkout_url = self.stripe_handler.create_checkout_session(update.effective_user.id)
            await self._send_text(update, f"💳 Subscribe here: {checkout_url}")
        except Exception as exc:
            _logger.exception("Checkout session creation failed: %s", exc)
            await self._send_text(update, "Unable to start checkout right now. Please try later.")

    async def _tomorrow(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        user = self.db.get_user(update.effective_user.id)
        if not user:
            await self._send_text(update, "Please send /start to set up your profile first.")
            return
        try:
            recent = self.db.get_recent_meals(update.effective_user.id)
            plan = self.openai_handler.generate_plan_json(user, "tomorrow", recent)
            self.db.save_plan(update.effective_user.id, "tomorrow", plan)
            text = self._format_plan_text(user.get("name", "there"), plan, "Your Plan for Tomorrow")
            await self._send_text(update, text, parse_mode="MarkdownV2")
        except Exception as exc:
            _logger.exception("Failed to prepare tomorrow plan: %s", exc)
            await self._send_text(update, "Couldn't prepare a plan right now. Please try later.")

    # -------------------- Callback & Messages --------------------

    async def _button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        mapping = {
            "tomorrow_plan": self._tomorrow,
            "subscribe": self._subscribe,
            "help": self._help,
        }
        handler = mapping.get(query.data)
        if handler:
            await handler(update, context)
        else:
            await query.edit_message_text("Unknown option.")

    async def _handle_message(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        text = update.message.text or ""
        parts = [item.strip() for item in text.replace("\n", ",").split(",") if item.strip()]
        if len(parts) < 8:
            await self._send_text(update, "Please send all 8 profile details as described in /start.")
            return

        try:
            name, age, gender, height, weight, activity, diet, goal = parts[:8]
            profile = {
                "name": name,
                "age": int(age),
                "gender": gender.upper(),
                "height_cm": int(str(height).replace("cm", "")),
                "weight_kg": int(str(weight).replace("kg", "")),
                "activity": activity.capitalize(),
                "diet": diet.capitalize(),
                "goal_kg": int(str(goal).replace("kg", "")),
            }
            self.db.update_user(update.effective_user.id, **profile)
            await self._send_text(
                update,
                f"🔥 Great, {_md(name)}! Preparing your personalized plan…",
                parse_mode="MarkdownV2",
            )
            plan = self.openai_handler.generate_plan_json(profile, "today")
            self.db.save_plan(update.effective_user.id, "today", plan)
            text_plan = self._format_plan_text(name, plan, "Your Personalized Plan")
            await self._send_text(update, text_plan, parse_mode="MarkdownV2")
        except Exception as exc:
            _logger.exception("Profile handling failed: %s", exc)
            await self._send_text(update, "Something went wrong while updating your profile.")

    # -------------------- Utils --------------------

    def _format_plan_text(self, name: str, plan: Dict[str, Any], title: str) -> str:
        lines: List[str] = [f"*{_md(title)}* for {_md(name)}\n"]
        for meal in plan.get("meals", []):
            lines.append(f"🍴 *{_md(meal.get('meal', 'Meal'))}*: {_md(meal.get('title', ''))}")
            description = meal.get("description")
            if description:
                lines.append(_md(description))
            calories = meal.get("calories")
            if calories:
                lines.append(f"🔥 {_md(str(calories))} kcal")
            lines.append("")
        if plan.get("total_calories"):
            lines.append(f"📊 Total: {_md(str(plan['total_calories']))} kcal")
        if plan.get("tip"):
            lines.append(f"💡 Tip: {_md(plan['tip'])}")
        return "\n".join(lines).strip()


