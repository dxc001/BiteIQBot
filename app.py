# ============================================
# app.py — BiteIQBot Flask + Telegram Webhook
# ============================================

from gevent import monkey
monkey.patch_all()

import asyncio
import threading
import logging
from flask import Flask, request, jsonify

from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot
from scheduler import ReminderScheduler
from config import WEBHOOK_URL

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("app")

# ---------- Flask ----------
app = Flask(__name__)

# ---------- Core Components ----------
db = Database()
openai_handler = OpenAIHandler(db)
stripe_handler = StripeHandler(db)
telegram_bot = TelegramBot(db, openai_handler, stripe_handler)
scheduler = ReminderScheduler(db, openai_handler)

# ==========================================================
#        GLOBAL EVENT LOOP (for Telegram bot + scheduler)
# ==========================================================
bot_loop = asyncio.new_event_loop()

def bot_loop_runner():
    asyncio.set_event_loop(bot_loop)

    async def init():
        # Initialize and start the PTB Application
        await telegram_bot.application.initialize()
        await telegram_bot.application.start()
        logger.info("✅ Telegram application started in background loop")

        # Set Telegram webhook
        await telegram_bot.application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
        logger.info(f"✅ Telegram webhook set to: {WEBHOOK_URL}/webhook")

        # Start reminder scheduler
        scheduler.start()
        logger.info("⏰ Reminder scheduler started")

    bot_loop.create_task(init())
    bot_loop.run_forever()

# Start the background bot thread
threading.Thread(target=bot_loop_runner, daemon=True).start()


# ==========================================================
#                    FLASK ENDPOINTS
# ==========================================================

@app.route("/")
def index():
    """Simple homepage/health route"""
    return jsonify({"status": "online", "service": "BiteIQBot"}), 200


@app.route("/health")
def health():
    return jsonify({"status": "healthy"}), 200


# --- Telegram webhook endpoint ---
@app.post("/webhook")
def telegram_webhook():
    """Receive updates from Telegram and dispatch them asynchronously."""
    try:
        from telegram import Update

        data = request.get_json(force=True)
        update = Update.de_json(data, telegram_bot.application.bot)
        logger.info(f"📩 Incoming update: {update.to_dict()}")

        # Run PTB handler asynchronously in the background loop
        fut = asyncio.run_coroutine_threadsafe(
            telegram_bot.application.process_update(update),
            bot_loop,
        )

        # Optional: log handler result errors
        def _cb(f):
            try:
                f.result()
            except Exception as e:
                logger.exception("❌ Error during update processing: %s", e)

        fut.add_done_callback(_cb)
        return "OK", 200

    except Exception as e:
        logger.exception("❌ Error processing Telegram webhook: %s", e)
        return jsonify({"error": str(e)}), 500


# --- Stripe webhook endpoint ---
@app.post("/stripe-webhook")
def stripe_webhook():
    """Handle Stripe payment webhooks (extend as needed)."""
    try:
        event = request.get_json(force=True)
        logger.info(f"💳 Stripe event received: {event.get('type')}")
        # Add your specific event handling here
        return "OK", 200
    except Exception as e:
        logger.exception("❌ Stripe webhook error: %s", e)
        return jsonify({"error": str(e)}), 500


# ==========================================================
#                 LOCAL DEBUG RUNNER
# ==========================================================
if __name__ == "__main__":
    import os
    PORT = int(os.environ.get("PORT", 8080))
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

    logger.info("🚀 Starting BiteIQBot Flask server...")
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG)



