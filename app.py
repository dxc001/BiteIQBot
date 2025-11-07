import os
import asyncio
import logging
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application

from database import Database as SupabaseDB
from telegram_bot import TelegramBot
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler

# ──────────────────────────────
# Logging setup
# ──────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# ──────────────────────────────
# Flask setup
# ──────────────────────────────
app = Flask(__name__)

# ──────────────────────────────
# Initialize core components
# ──────────────────────────────
db = SupabaseDB()
openai_handler = OpenAIHandler(db=db)
stripe_handler = StripeHandler(db=db)
bot = TelegramBot(db=db, openai_handler=openai_handler, stripe_handler=stripe_handler)

# Telegram application reference (so we can process updates)
application: Application = bot.application

# ──────────────────────────────
# Health endpoint
# ──────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "BiteIQBot is live ⚡", 200


# ──────────────────────────────
# Telegram webhook endpoint
# ──────────────────────────────
@app.post("/webhook")
def webhook():
    """Receive Telegram updates from Telegram servers."""
    try:
        update_data = request.get_json(force=True)
        logger.info(f"📩 Incoming Telegram update: {update_data}")

        # Schedule processing asynchronously in background
        async def process():
            update = Update.de_json(update_data, application.bot)
            await application.process_update(update)

        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.create_task(process())

        # Respond instantly so Render doesn't timeout
        return "OK", 200

    except Exception as e:
        logger.exception(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────
# Stripe webhook endpoint
# ──────────────────────────────
@app.post("/stripe-webhook")
def stripe_webhook():
    """Handle Stripe subscription and payment events."""
    try:
        event = request.get_json(force=True)
        logger.info(f"💳 Stripe event received: {event.get('type')}")
        # You can later add: stripe_handler.process_event(event)
        return "OK", 200
    except Exception as e:
        logger.exception(f"❌ Stripe webhook error: {e}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────
# Auto-register Telegram webhook on startup
# ──────────────────────────────
@app.before_serving
async def setup_webhook():
    """Ensure Telegram knows where to send updates."""
    webhook_url = "https://biteiqbot.onrender.com/webhook"
    try:
        await application.bot.set_webhook(webhook_url)
        logger.info(f"🔗 Webhook registered successfully: {webhook_url}")
    except Exception as e:
        logger.error(f"⚠️ Failed to set webhook automatically: {e}")


# ──────────────────────────────
# Start (only for local debugging)
# ──────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Running locally on port {port}")
    app.run(host="0.0.0.0", port=port)





