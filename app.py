# ==========================================================
# app.py — Flask + Telegram bot unified server (Render-ready)
# ==========================================================

import asyncio
import logging
import os
from flask import Flask, request, jsonify
from telegram import Update
from telegram.error import TelegramError

from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot
from scheduler import ReminderScheduler
from config import WEBHOOK_URL

# ----------------------------------------------------------
# Logging setup
# ----------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("app")

# ----------------------------------------------------------
# Core initialization
# ----------------------------------------------------------
app = Flask(__name__)

db = Database()
openai_handler = OpenAIHandler(db)
stripe_handler = StripeHandler(db)
telegram_bot = TelegramBot(db, openai_handler, stripe_handler)
scheduler = ReminderScheduler(db, openai_handler)

# ----------------------------------------------------------
# Async startup
# ----------------------------------------------------------
async def startup():
    """Initialize Telegram bot and scheduler."""
    await telegram_bot.application.initialize()
    await telegram_bot.application.start()
    await telegram_bot.application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info(f"✅ Webhook set to {WEBHOOK_URL}/webhook")
    scheduler.start()
    logger.info("⏰ Scheduler started")

loop = asyncio.get_event_loop()
loop.run_until_complete(startup())

# ----------------------------------------------------------
# Routes
# ----------------------------------------------------------
@app.get("/")
def index():
    return jsonify({"status": "online", "service": "BiteIQBot"}), 200

@app.get("/health")
def health():
    return jsonify({"status": "healthy"}), 200

@app.post("/webhook")
def telegram_webhook():
    """Receive Telegram webhook and safely dispatch to async bot."""
    try:
        data = request.get_json(force=True)
        logger.info(f"📩 Incoming update: {data}")
        update = Update.de_json(data, telegram_bot.application.bot)

        async def process():
            try:
                await telegram_bot.application.process_update(update)
            except TelegramError as te:
                logger.error(f"⚠️ Telegram API error: {te}")
            except Exception as e:
                logger.exception(f"❌ Error processing update: {e}")

        # Run coroutine safely whether loop already running or not
        try:
            asyncio.run(process())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.create_task(process())

        return "OK", 200

    except Exception as e:
        logger.exception(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

@app.post("/stripe-webhook")
def stripe_webhook():
    """Handle Stripe events."""
    try:
        event = request.get_json(force=True)
        logger.info(f"💳 Stripe event received: {event.get('type')}")
        # TODO: implement subscription update handling
        return "OK", 200
    except Exception as e:
        logger.exception(f"❌ Stripe webhook error: {e}")
        return jsonify({"error": str(e)}), 500

# ----------------------------------------------------------
# Entry point
# ----------------------------------------------------------
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Starting BiteIQBot on port {PORT}")
    app.run(host="0.0.0.0", port=PORT) 


