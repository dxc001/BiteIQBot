import logging
import asyncio
from datetime import date, timedelta
from typing import Any, Dict, List
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.helpers import escape_markdown
from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram_bot")

# === Markdown escape utility ===
MD_RISKY = ["\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]

def md(text: Any) -> str:
    """Escape risky characters for MarkdownV2"""
    s = str(text)
    s = escape_markdown(s, version=2)
    for ch in MD_RISKY:
        s = s.replace(ch, f"\\{ch}")
    return s


class TelegramBot:
    def __init__(self, db: Database, openai_handler: OpenAIHandler, stripe_handler: StripeHandler):
        self.db = db
        self.openai = openai_handler
        self.stripe = stripe_handler
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        self.awaiting_recipe: Dict[int, bool] = {}
        self.awaiting_question: Dict[int, bool] = {}

        self.setup_handlers()

    async def initialize(self):
        """Initialize Telegram application"""
        await self.application.initialize()
        await self.application.start()
        logger.info("🤖 Telegram bot initialized")

    # === HANDLERS SETUP ===
    def setup_handlers(self):
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("tomorrow", self.tomorrow_command))
        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    # === /START ===
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            user_id = update.effective_user.id
            username = update.effective_user.username
            logger.info(f"➡️ /start triggered by {username}")

            # Create or update user in Supabase
            user = self.db.get_user(user_id)
            if not user:
                self.db.create_user(user_id, username)

            welcome = (
                "👋 *Welcome to BiteIQBot — your smart nutrition coach!* 🥗\n\n"
                "To personalize your plan, please send the following 8 details "
                "_(each on a new line or separated by commas)_: \n\n"
                "1️⃣ Name\n"
                "2️⃣ Age\n"
                "3️⃣ Gender (M/F)\n"
                "4️⃣ Height (cm)\n"
                "5️⃣ Weight (kg)\n"
                "6️⃣ Activity level (low / medium / high)\n"
                "7️⃣ Dietary restrictions (or none)\n"
                "8️⃣ Goal weight (kg)\n\n"
                "📅 Your daily plan will be automatically sent at *06:00*!"
            )

            await update.message.reply_text(welcome, parse_mode="MarkdownV2")

        except Exception as e:
            logger.exception(f"❌ Error in /start: {e}")
            await update.message.reply_text(
                "⚠️ Sorry, something went wrong while starting the bot. Please try again later."
            )

    # === /MENU ===
    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Main menu for user"""
        try:
            keyboard = [
                [InlineKeyboardButton("📅 Tomorrow Plan", callback_data="tomorrow_plan")],
                [InlineKeyboardButton("💳 Subscribe", callback_data="subscribe")],
                [InlineKeyboardButton("❓ Help", callback_data="help")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "🍽️ *Welcome to BiteIQ Menu!*\n\n"
                "Choose what you’d like to do:",
                reply_markup=reply_markup,
                parse_mode="MarkdownV2",
            )
        except Exception as e:
            logger.error(f"❌ menu_command error: {e}")
            await update.message.reply_text("⚠️ Something went wrong while opening the menu.")

    # === /HELP ===
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "ℹ️ *BiteIQBot Commands:*\n\n"
            "• `/start` — Restart setup\n"
            "• `/menu` — Open the main menu\n"
            "• `/tomorrow` — Get tomorrow’s plan\n"
            "• `/subscribe` — Manage your subscription\n\n"
            "💡 Just send your profile details again anytime to update them!"
        )
        await update.message.reply_text(help_text, parse_mode="MarkdownV2")

    # === /SUBSCRIBE ===
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            checkout_url = self.stripe.create_checkout_session(update.effective_user.id)
            await update.message.reply_text(f"💳 Click below to subscribe:\n{checkout_url}")
        except Exception as e:
            logger.error(f"Stripe error: {e}")
            await update.message.reply_text("❌ Unable to create a Stripe checkout session right now.")

    # === /TOMORROW ===
    async def tomorrow_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = self.db.get_user(update.effective_user.id)
        if not user:
            await update.message.reply_text("⚠️ Please set up your profile first with /start.")
            return

        name = user["name"]
        meals = self.openai.generate_plan_json(user, "tomorrow")
        tomorrow = date.today() + timedelta(days=1)

        self.db.save_plan(user["telegram_id"], tomorrow, meals)
        text = self.format_plan_text(name, meals, "Your Plan for Tomorrow")

        await update.message.reply_text(text, parse_mode="MarkdownV2")

    # === CALLBACKS ===
    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if query.data == "tomorrow_plan":
            await self.tomorrow_command(update, context)
        elif query.data == "subscribe":
            await self.subscribe_command(update, context)
        elif query.data == "help":
            await self.help_command(update, context)
        else:
            await query.edit_message_text("⚠️ Unknown option selected.")

    # === MESSAGE HANDLER ===
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle free text (user profile input)"""
        try:
            text = update.message.text
            parts = [p.strip() for p in text.replace("\n", ",").split(",") if p.strip()]
            if len(parts) < 8:
                await update.message.reply_text(
                    "⚠️ Please provide all 8 details as described in /start."
                )
                return

            name, age, gender, height, weight, activity, diet, goal = parts[:8]
            data = {
                "name": name,
                "age": int(age),
                "gender": gender.upper(),
                "height_cm": int(height.replace("cm", "")),
                "weight_kg": int(weight.replace("kg", "")),
                "activity": activity.capitalize(),
                "diet": diet.capitalize(),
                "goal_kg": int(goal.replace("kg", "")),
            }

            self.db.update_user(update.effective_user.id, data)
            await update.message.reply_text(
                f"🔥 Great, {md(name)}! Preparing your personalized plan…",
                parse_mode="MarkdownV2",
            )

            plan = self.openai.generate_plan_json(data, "today")
            self.db.save_plan(update.effective_user.id, date.today(), plan)
            text = self.format_plan_text(name, plan, "Your Personalized Plan")
            await update.message.reply_text(text, parse_mode="MarkdownV2")

        except Exception as e:
            logger.exception(f"❌ handle_message error: {e}")
            await update.message.reply_text("⚠️ Something went wrong, please try again later.")

    # === FORMAT PLAN ===
    def format_plan_text(self, name: str, plan: Dict[str, Any], title: str) -> str:
        try:
            meals = plan.get("meals", [])
            text = f"*{md(title)}* for {md(name)}:\n\n"
            for meal in meals:
                text += f"🍴 *{md(meal.get('title',''))}*\n"
                text += f"🕒 {md(meal.get('time',''))}\n"
                text += f"{md(meal.get('description',''))}\n\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Error formatting plan: {e}")
            return "⚠️ Could not format meal plan."



