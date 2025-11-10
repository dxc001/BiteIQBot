from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from database import Database
from openai_handler import OpenAIHandler
from telegram import Bot
from telegram.helpers import escape_markdown
from config import TELEGRAM_BOT_TOKEN
import logging
from datetime import date, timedelta
import asyncio

logger = logging.getLogger(__name__)

MD_RISKY = ["\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"]

def md(text: str) -> str:
    """Make text safe for MarkdownV2"""
    s = str(text)
    s = escape_markdown(s, version=2)
    for ch in MD_RISKY:
        s = s.replace(ch, f"\\{ch}")
    return s

class Scheduler:
    def __init__(self, db: Database, openai_handler: OpenAIHandler):
        self.db = db
        self.openai = openai_handler
        self.scheduler = BackgroundScheduler()
        self.bot = Bot(token=TELEGRAM_BOT_TOKEN)

    def send_daily_plan(self):
        """Send daily meal plan to all subscribed users at 06:00"""
        try:
            users = self.db.get_all_users()
            today = date.today()

            for user in users:
                telegram_id = user['telegram_id']

                if not self.db.has_active_subscription(telegram_id):
                    continue

                if not user.get('name'):
                    continue

                try:
                    name = user.get("name", "there")
                    recent = self.db.get_recent_meals(telegram_id, 7)
                    plan = self.openai.generate_plan_json(user, "today", recent)

                    self.db.save_plan(telegram_id, today, plan)
                    self.db.add_meals_to_history(telegram_id, [m.get("title", "") for m in plan.get("meals", [])])

                    lines = []
                    lines.append(f"🥗 *Your Fresh Daily Plan* – *{md(name)}*")
                    lines.append("━━━━━━━━━━━━━━━")

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

                    txt = "\n".join(lines)

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.bot.send_message(
                        chat_id=telegram_id,
                        text=txt,
                        parse_mode="MarkdownV2"
                    ))
                    loop.close()
                    logger.info(f"Sent daily plan to user {telegram_id}")
                except Exception as e:
                    logger.error(f"Error sending daily plan to {telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Error in send_daily_plan: {e}")

    def send_reminder(self, kind: str):
        """Send reminders to users with reminders enabled"""
        try:
            telegram_ids = self.db.get_users_with_reminders()

            for telegram_id in telegram_ids:
                if not self.db.has_active_subscription(telegram_id):
                    continue

                user = self.db.get_user(telegram_id)
                name = user.get("name", "there") if user else "there"

                try:
                    if kind == "breakfast":
                        text = f"🥣 {md(f'Good morning, {name}!')} Time for breakfast\\."
                    elif kind == "hydration":
                        text = f"💧 {md(f'Quick hydration check, {name}!')} Take a moment to drink water\\."
                    elif kind == "lunch":
                        text = f"🍱 {md(f'Lunchtime, {name}!')} Refuel smart\\."
                    elif kind == "dinner":
                        text = f"🌇 {md(f'Dinner time, {name}!')} Keep it light\\."
                    else:
                        text = f"🔔 {md(f'Hey {name}, gentle reminder to eat mindfully.')}"

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self.bot.send_message(
                        chat_id=telegram_id,
                        text=text,
                        parse_mode="MarkdownV2"
                    ))
                    loop.close()
                    logger.info(f"Sent {kind} reminder to user {telegram_id}")
                except Exception as e:
                    logger.error(f"Error sending {kind} reminder to {telegram_id}: {e}")

        except Exception as e:
            logger.error(f"Error in send_reminder: {e}")

    def start(self):
        """Start the scheduler with all jobs"""
        self.scheduler.add_job(
            self.send_daily_plan,
            CronTrigger(hour=6, minute=0),
            id="daily_plan",
            replace_existing=True
        )

        self.scheduler.add_job(
            lambda: self.send_reminder("breakfast"),
            CronTrigger(hour=8, minute=0),
            id="reminder_breakfast",
            replace_existing=True
        )

        self.scheduler.add_job(
            lambda: self.send_reminder("hydration"),
            CronTrigger(hour=10, minute=0),
            id="reminder_hydration_morning",
            replace_existing=True
        )

        self.scheduler.add_job(
            lambda: self.send_reminder("lunch"),
            CronTrigger(hour=13, minute=0),
            id="reminder_lunch",
            replace_existing=True
        )

        self.scheduler.add_job(
            lambda: self.send_reminder("hydration"),
            CronTrigger(hour=15, minute=0),
            id="reminder_hydration_afternoon",
            replace_existing=True
        )

        self.scheduler.add_job(
            lambda: self.send_reminder("dinner"),
            CronTrigger(hour=18, minute=0),
            id="reminder_dinner",
            replace_existing=True
        )

        self.scheduler.start()
        logger.info("Reminder scheduler started with all jobs")

    def shutdown(self):
        """Shutdown the scheduler"""
        self.scheduler.shutdown()
        logger.info("Reminder scheduler stopped")
