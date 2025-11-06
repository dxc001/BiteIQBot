# ==========================================================
# app.py — unified Flask + Telegram bot event loop for Render
# ==========================================================

import asyncio
import logging
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application

from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot
from scheduler import ReminderScheduler
from config import WEBHOOK_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("app")

app = Flask(__name__)

# --- Core components ---
db = Database()
openai_handler = OpenAIHandler(db)
stripe_handler = StripeHandler(db)
telegram_bot = TelegramBot(db, openai_handler, stripe_handler)
scheduler = ReminderScheduler(db, openai_handler)


# ==========================================================
#            ASYNC STARTUP (Flask + TelegramBot)
# ==========================================================
async def startup():
    """Initialize Telegram bot & scheduler inside main event loop."""
    await telegram_bot.application.initialize()
    await telegram_bot.application.start()

    await telegram_bot.application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info(f"✅ Webhook set to {WEBHOOK_URL}/webhook")

    scheduler.start()
    logger.info("⏰ Scheduler started")


loop = asyncio.get_event_loop()
loop.run_until_complete(startup())


# ==========================================================
#                    FLASK ROUTES
# ==========================================================
@app.get("/")
def index():
    return jsonify({"status": "online", "service": "BiteIQBot"}), 200


@app.get("/health")
def health():
    return jsonify({"status": "healthy"}), 200


@app.post("/webhook")
def telegram_webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_bot.application.bot)
        logger.info(f"📩 Incoming update: {update.to_dict()}")

        asyncio.ensure_future(
            telegram_bot.application.process_update(update), loop=loop
        )

        return "OK", 200

    except Exception as e:
        logger.exception("❌ Webhook error: %s", e)
        return jsonify({"error": str(e)}), 500


@app.post("/stripe-webhook")
def stripe_webhook():
    try:
        event = request.get_json(force=True)
        logger.info(f"💳 Stripe event: {event.get('type')}")
        # handle stripe events here
        return "OK", 200
    except Exception as e:
        logger.exception("❌ Stripe webhook error: %s", e)
        return jsonify({"error": str(e)}), 500


# ==========================================================
#                    ENTRY POINT
# ==========================================================
if __name__ == "__main__":
    import os

    PORT = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Starting BiteIQBot on port {PORT}")
    app.run(host="0.0.0.0", port=PORT)


