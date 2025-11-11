import asyncio
import logging
from datetime import date
from typing import List

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SupabaseDB
from openai_handler import OpenAIHandler
from telegram_bot import TelegramBot

_logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self, db: SupabaseDB, openai_handler: OpenAIHandler, telegram_bot: TelegramBot):
        self.db = db
        self.openai_handler = openai_handler
        self.telegram_bot = telegram_bot
        self._scheduler = BackgroundScheduler()
        self._started = False

    def _format_plan_message(self, user: dict, plan: dict) -> str:
        lines: List[str] = ["🥗 BiteIQ Daily Plan"]
        if user.get("name"):
            lines.append(f"Hi {user['name']}!")
        for meal in plan.get("meals", []):
            lines.append("")
            lines.append(f"{meal.get('meal', 'Meal')}: {meal.get('title', '')}")
            desc = meal.get("description")
            if desc:
                lines.append(desc)
            calories = meal.get("calories")
            if calories:
                lines.append(f"Calories: {calories}")
        if plan.get("total_calories"):
            lines.append("")
            lines.append(f"Total: {plan['total_calories']} kcal")
        if plan.get("tip"):
            lines.append(f"Tip: {plan['tip']}")
        return "\n".join(lines)

    def _send_daily_plan(self):
        _logger.info("Running daily meal plan job")
        users = self.db.get_all_users()
        for user in users:
            telegram_id = user.get("telegram_id")
            if not telegram_id:
                continue
            if not self.db.has_active_subscription(telegram_id):
                continue
            try:
                recent_meals = self.db.get_recent_meals(telegram_id)
                plan = self.openai_handler.generate_plan_json(user, "today", recent_meals)
                self.db.save_plan(telegram_id, date.today().isoformat(), plan)
                self.db.add_meals_to_history(
                    telegram_id, [meal.get("title") for meal in plan.get("meals", [])]
                )
                message = self._format_plan_message(user, plan)
                asyncio.run(
                    self.telegram_bot.application.bot.send_message(
                        chat_id=telegram_id,
                        text=message,
                    )
                )
            except Exception as exc:
                _logger.exception("Failed to send daily plan to %s: %s", telegram_id, exc)

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.add_job(
            self._send_daily_plan,
            CronTrigger(hour=6, minute=0),
            id="daily-plan",
            replace_existing=True,
        )
        self._scheduler.start()
        self._started = True
        _logger.info("Scheduler started")

    def shutdown(self) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False
        _logger.info("Scheduler stopped")
