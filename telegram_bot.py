from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.helpers import escape_markdown
from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from config import TELEGRAM_BOT_TOKEN, WEBHOOK_URL
import logging
import re
from datetime import date, timedelta
from typing import Dict, Any, List, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MD_RISKY = ["\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]

def md(text: Any) -> str:
    """Make text safe for MarkdownV2"""
    s = str(text)
    s = escape_markdown(s, version=2)
    for ch in MD_RISKY:
        s = s.replace(ch, f"\\{ch}")
    return s

def bold(text: Any) -> str:
    """Make text bold in MarkdownV2"""
    return f"*{md(text)}*"


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
        """Initialize the application"""
        await self.application.initialize()
        await self.application.start()

    def setup_handlers(self):
        """Setup all command and message handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("menu", self.menu_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("tomorrow", self.tomorrow_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))

        self.application.add_handler(CallbackQueryHandler(self.button_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    def is_subscribed(self, user: Optional[Dict[str, Any]]) -> bool:
        """Check if user has active subscription"""
        if not user:
            return False
        telegram_id = user.get("telegram_id")
        return self.db.has_active_subscription(telegram_id)

    def parse_profile_input(self, txt: str) -> Optional[Tuple]:
        """Parse user profile from text input"""
        parts = [p.strip() for p in (txt.split(",") if "," in txt else txt.splitlines()) if p.strip()]
        if len(parts) != 8:
            return None

        name = parts[0]
        try:
            age = int(re.sub(r"[^\d]", "", parts[1]))
            gender = parts[2]
            height_cm = float(re.sub(r"[^\d.]", "", parts[3]))
            weight_kg = float(re.sub(r"[^\d.]", "", parts[4]))
            activity = parts[5]
            diet = parts[6]
            goal_kg = float(re.sub(r"[^\d.]", "", parts[7]))
        except Exception:
            return None

        return (name, age, gender, height_cm, weight_kg, activity, diet, goal_kg)

    def format_plan_text(self, name: str, plan: dict, title: str = "Your Personalized Meal Plan") -> str:
        """Format meal plan for Telegram with MarkdownV2"""
        lines = [f"🥗 *{md(title)}* – *{md(name)}*", "━━━━━━━━━━━━━━━"]
        emap = {"Breakfast": "🍳", "Lunch": "🥗", "Dinner": "🍽️", "Snack": "🥤"}

        for m in plan.get("meals", []):
            meal = m.get("meal", "Meal")
            emoji = emap.get(meal, "🍴")
            ttl = m.get("title", "")
            desc = m.get("description", "")
            cal = m.get("calories", "")
            lines.append(f"\n{emoji} *{md(meal)}*: {md(ttl)}")
            lines.append(f"_{md(desc)}_")
            lines.append(f"🔥 *{md(str(cal))} kcal*")

        lines.append("\n━━━━━━━━━━━━━━━")
        if "total_calories" in plan:
            lines.append(f"📊 *Total:* {md(plan['total_calories'])} kcal")
        if plan.get("tip"):
            lines.append(f"💡 *Tip:* {md(plan['tip'])}")
        return "\n".join(lines)

    def format_recipe_text(self, title: str, content: str) -> str:
        """Format recipe for Telegram"""
        content = re.sub(r"\*\*", "*", content).strip()
        return "\n".join([
            f"👩‍🍳 *Recipe for {md(title)}*",
            "━━━━━━━━━━━━━━━",
            md(content),
            "━━━━━━━━━━━━━━━",
        ])

    def build_recipe_buttons(self, meals: List[dict]) -> InlineKeyboardMarkup:
        """Build inline keyboard for recipe selection"""
        buttons = []
        for m in meals:
            if m.get("meal") in ["Breakfast", "Lunch", "Dinner"]:
                icon = {"Breakfast": "🍳", "Lunch": "🥗", "Dinner": "🍽️"}[m["meal"]]
                title = m.get("title") or m["meal"]
                buttons.append([InlineKeyboardButton(f"{icon} {m['meal']} Recipe", callback_data=f"recipe|{title}")])
        if not buttons:
            buttons.append([InlineKeyboardButton("👩‍🍳 Get a Recipe", callback_data="req_recipe")])
        return InlineKeyboardMarkup(buttons)

    def menu_keyboard(self, reminders_on: bool, subscribed: bool) -> InlineKeyboardMarkup:
        """Build main menu keyboard"""
        rows = [
            [InlineKeyboardButton("🍽️ Tomorrow's Plan", callback_data="menu_tomorrow")],
            [InlineKeyboardButton("👩‍🍳 Get a Recipe", callback_data="req_recipe")],
            [InlineKeyboardButton("❓ Ask a question", callback_data="ask_q")],
        ]
        rows.append([
            InlineKeyboardButton("🔕 Stop reminders" if reminders_on else "🔔 Activate reminders",
                                 callback_data="rem_stop" if reminders_on else "rem_start")
        ])
        rows.append([
            InlineKeyboardButton("💳 Manage subscription" if subscribed else "💳 Subscribe",
                                 callback_data="manage_sub" if subscribed else "subscribe")
        ])
        return InlineKeyboardMarkup(rows)

    # ✅ FIXED indentation: now class-level method
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        logger.info(f"➡️ /start triggered by user: {user.id} ({user.username})")

        try:
            created_user = self.db.get_or_create_user(
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
            )
            logger.info(f"✅ User record ready: {created_user}")

            intro_text = (
                f"👋 *Welcome to BiteIQBot*, {md(user.first_name)} — your smart nutrition coach! 🥗\n\n"
                "To personalize your plan, please send the following 8 details (each on a new line or separated by commas):\n\n"
                "1️⃣ Name\n"
                "2️⃣ Age\n"
                "3️⃣ Gender (M/F)\n"
                "4️⃣ Height (cm)\n"
                "5️⃣ Weight (kg)\n"
                "6️⃣ Activity level (low / medium / high)\n"
                "7️⃣ Dietary restrictions (or 'none')\n"
                "8️⃣ Goal weight (kg)\n\n"
                "📅 Your daily plan will be automatically sent at 06:00."
            )

            await update.message.reply_text(
                intro_text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
            await update.message.reply_text(
                "📋 Type /menu anytime to open your main options.",
                parse_mode="MarkdownV2",
            )
            logger.info(f"✅ /start message sent to {user.id}")

        except Exception as e:
            logger.error(f"❌ Error in /start: {e}", exc_info=True)
            try:
                await update.message.reply_text(
                    "⚠️ Sorry, something went wrong while starting the bot\\. Please try again later\\.",
                    parse_mode="MarkdownV2",
                )
            except Exception as e2:
                logger.error(f"⚠️ Failed to send error message: {e2}", exc_info=True)

    # (rest of file stays identical — menu_command, help_command, etc.)



    async def menu_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /menu command"""
        uid = update.effective_user.id
        u = self.db.get_user(uid)
        kb = self.menu_keyboard(
            bool(u and u.get("reminders")),
            bool(self.is_subscribed(u))
        )
        await update.message.reply_text("📋 " + bold("Menu"), reply_markup=kb, parse_mode="MarkdownV2")

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        txt = (
            f"{bold('What I do:')}\n"
            "\\- Generate daily personalized meal plans\n"
            "\\- Send simple reminders \\(meals \\+ hydration\\)\n"
            "\\- Provide minimal, recipe\\-style answers\n\n"
            f"{bold('Quick commands:')}\n"
            "/menu – open menu\n"
            "/tomorrow – get tomorrow's plan"
        )
        await update.message.reply_text(txt, parse_mode="MarkdownV2")

    async def tomorrow_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tomorrow command"""
        uid = update.effective_user.id
        u = self.db.get_user(uid)

        if not u or not u.get('name'):
            await update.message.reply_text("Please set up your profile first with /start\\.", parse_mode="MarkdownV2")
            return

        if not self.is_subscribed(u):
            await update.message.reply_text("🔒 Please /subscribe to get tomorrow's plan\\.", parse_mode="MarkdownV2")
            return

        name = u["name"]
        recent = self.db.get_recent_meals(uid, 7)
        plan = self.openai.generate_plan_json(u, "tomorrow", recent)

        tomorrow = date.today() + timedelta(days=1)
        self.db.save_plan(uid, tomorrow, plan)
        self.db.add_meals_to_history(uid, [m.get("title", "") for m in plan.get("meals", [])])

        txt = self.format_plan_text(name, plan, "Your Plan for Tomorrow")
        await update.message.reply_text(txt, parse_mode="MarkdownV2", reply_markup=self.build_recipe_buttons(plan.get("meals", [])))

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /subscribe command"""
        uid = update.effective_user.id
        try:
            checkout_url = self.stripe.create_checkout_session(uid)
            await update.message.reply_text(f"💳 Subscribe here:\n{checkout_url}")
        except Exception as e:
            logger.error(f"Stripe error: {e}")
            await update.message.reply_text("❌ Sorry, there was an error creating your checkout session\\. Please try again later\\.", parse_mode="MarkdownV2")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle all text messages"""
        uid = update.effective_user.id
        text = update.message.text.strip()

        if self.awaiting_recipe.get(uid):
            self.awaiting_recipe.pop(uid, None)
            meal_title = text
            profile = self.db.get_user(uid)
            if not self.is_subscribed(profile):
                await update.message.reply_text("🔒 Please /subscribe to use recipes\\.", parse_mode="MarkdownV2")
                return

            r = self.openai.generate_recipe_text(meal_title, profile)
            await update.message.reply_text(self.format_recipe_text(meal_title, r), parse_mode="MarkdownV2")
            return

        if self.awaiting_question.get(uid):
            self.awaiting_question.pop(uid, None)
            profile = self.db.get_user(uid)
            if not self.is_subscribed(profile):
                await update.message.reply_text("🔒 Please /subscribe to ask questions\\.", parse_mode="MarkdownV2")
                return

            ans = self.openai.get_ai_response(uid, text)
            await update.message.reply_text(md(ans), parse_mode="MarkdownV2")
            return

        parsed = self.parse_profile_input(text)
        if parsed:
            (name, age, gender, height_cm, weight_kg, activity, diet, goal_kg) = parsed
            self.db.upsert_user_profile(uid, name, age, gender, height_cm, weight_kg, activity, diet, goal_kg)

            u = self.db.get_user(uid)

            await update.message.reply_text(md(f"🔥 Great, {name}! Preparing your personalized plan…"), parse_mode="MarkdownV2")
            await context.bot.send_chat_action(chat_id=uid, action="typing")

            recent = self.db.get_recent_meals(uid, 7)
            profile = u or {
                "name": name, "age": age, "gender": gender, "height_cm": height_cm,
                "weight_kg": weight_kg, "activity": activity, "diet": diet, "goal_kg": goal_kg
            }
            plan = self.openai.generate_plan_json(profile, "today", recent)
            self.db.save_plan(uid, date.today(), plan)
            self.db.add_meals_to_history(uid, [m.get("title", "") for m in plan.get("meals", [])])

            txt = self.format_plan_text(name, plan, "Your Personalized Meal Plan")
            await update.message.reply_text(txt, parse_mode="MarkdownV2", reply_markup=self.build_recipe_buttons(plan.get("meals", [])))

            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Yes — meal & hydration reminders", callback_data="rem_start")],
                [InlineKeyboardButton("❌ No thanks", callback_data="rem_stop")]
            ])
            await update.message.reply_text("🔔 Enable day reminders?", reply_markup=kb)
            return

        if not any(k in text.lower() for k in [
            "diet", "calorie", "protein", "carb", "fat", "meal", "weight", "nutrition", "kcal",
            "recipe", "breakfast", "lunch", "dinner"
        ]):
            await update.message.reply_text(
                "💬 I'm your nutrition coach — I answer only diet \\& meal questions\\.\n"
                "Send your profile \\(8 details\\) to get started\\.",
                parse_mode="MarkdownV2"
            )
            return

        profile = self.db.get_user(uid)
        if not self.is_subscribed(profile):
            await update.message.reply_text("🔒 Please /subscribe to chat with your coach\\.", parse_mode="MarkdownV2")
            return

        ans = self.openai.get_ai_response(uid, text)
        await update.message.reply_text(md(ans), parse_mode="MarkdownV2")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button callbacks"""
        q = update.callback_query
        await q.answer()

        uid = q.from_user.id
        data = q.data or ""
        u = self.db.get_user(uid)

        if data == "rem_start":
            self.db.set_reminders(uid, True)
            await q.edit_message_text("🔔 Reminders ON: 08:00, 10:00, 13:00, 15:00, 18:00\\.", parse_mode="MarkdownV2")

        elif data == "rem_stop":
            self.db.set_reminders(uid, False)
            await q.edit_message_text("🔕 Reminders OFF\\. You'll still receive the daily 06:00 plan\\.", parse_mode="MarkdownV2")

        elif data == "menu_tomorrow":
            if not u or not u.get('name'):
                await q.edit_message_text("Please set up your profile first with /start\\.", parse_mode="MarkdownV2")
                return

            if not self.is_subscribed(u):
                await q.edit_message_text("🔒 Please /subscribe to get tomorrow's plan\\.", parse_mode="MarkdownV2")
                return

            name = u["name"]
            recent = self.db.get_recent_meals(uid, 7)
            plan = self.openai.generate_plan_json(u, "tomorrow", recent)

            tomorrow = date.today() + timedelta(days=1)
            self.db.save_plan(uid, tomorrow, plan)
            self.db.add_meals_to_history(uid, [m.get("title", "") for m in plan.get("meals", [])])

            txt = self.format_plan_text(name, plan, "Your Plan for Tomorrow")
            await context.bot.send_message(chat_id=uid, text=txt, parse_mode="MarkdownV2",
                                          reply_markup=self.build_recipe_buttons(plan.get("meals", [])))

        elif data == "req_recipe":
            if not self.is_subscribed(u):
                await q.edit_message_text("🔒 Please /subscribe to get recipes\\.", parse_mode="MarkdownV2")
                return

            self.awaiting_recipe[uid] = True
            await context.bot.send_message(chat_id=uid, text="👩‍🍳 Type the meal name you'd like a recipe for\\.", parse_mode="MarkdownV2")

        elif data.startswith("recipe|"):
            if not self.is_subscribed(u):
                await q.edit_message_text("🔒 Please /subscribe to get recipes\\.", parse_mode="MarkdownV2")
                return

            meal_title = data.split("|", 1)[1].strip() or "Meal"
            r = self.openai.generate_recipe_text(meal_title, u)
            await context.bot.send_message(chat_id=uid, text=self.format_recipe_text(meal_title, r), parse_mode="MarkdownV2")

        elif data == "ask_q":
            if not self.is_subscribed(u):
                await q.edit_message_text("🔒 Please /subscribe to ask questions\\.", parse_mode="MarkdownV2")
                return

            self.awaiting_question[uid] = True
            await context.bot.send_message(chat_id=uid, text="❓ Send your nutrition question \\(short\\)\\.", parse_mode="MarkdownV2")

        elif data == "subscribe":
            try:
                checkout_url = self.stripe.create_checkout_session(uid)
                await context.bot.send_message(chat_id=uid, text=f"💳 Subscribe here:\n{checkout_url}")
            except Exception as e:
                logger.error(f"Stripe error: {e}")
                await context.bot.send_message(chat_id=uid, text="❌ Sorry, there was an error creating your checkout session\\. Please try again later\\.", parse_mode="MarkdownV2")

        elif data == "manage_sub":
            customer_id = (u or {}).get("stripe_customer_id")
            if not customer_id:
                subscription_response = self.db.client.table('subscriptions').select('stripe_customer_id').eq('user_id', u['id']).maybe_single().execute()
                if subscription_response.data:
                    customer_id = subscription_response.data.get('stripe_customer_id')

            if not customer_id:
                await context.bot.send_message(chat_id=uid, text="No active subscription found\\.", parse_mode="MarkdownV2")
                return

            try:
                import stripe
                portal = stripe.billing_portal.Session.create(
                    customer=customer_id,
                    return_url=f"{WEBHOOK_URL}/settings"
                )
                await context.bot.send_message(chat_id=uid, text=f"🔧 Manage your subscription:\n{portal.url}")
            except Exception as e:
                logger.error(f"Stripe portal error: {e}")
                await context.bot.send_message(chat_id=uid, text="❌ Error creating portal session\\.", parse_mode="MarkdownV2")

