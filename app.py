import os
import asyncio
import logging
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application

from database import SupabaseDB
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

application: Application = bot.application

# ──────────────────────────────
# Health endpoint
# ──────────────────────────────
@app.route("/", methods=["GET"])
def home():
    return "✅ BiteIQBot is live", 200

# ──────────────────────────────
# Telegram webhook endpoint
# ──────────────────────────────
@app.post("/webhook")
def webhook():
    try:
        update_data = request.get_json(force=True)
        logger.info(f"📩 Incoming Telegram update: {update_data}")

        async def process():
            update = Update.de_json(update_data, application.bot)
            await application.process_update(update)

        # Run coroutine safely
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.create_task(process())

        return "OK", 200

    except Exception as e:
        logger.exception(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────
# Stripe webhook endpoint
# ──────────────────────────────
@app.post("/stripe-webhook")
def stripe_webhook():
    try:
        event = request.get_json(force=True)
        logger.info(f"💳 Stripe event received: {event.get('type')}")
        return "OK", 200
    except Exception as e:
        logger.exception(f"❌ Stripe webhook error: {e}")
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────
# Webhook registration logic (Flask 3 compatible)
# ──────────────────────────────
with app.app_context():
    try:
        webhook_url = "https://biteiqbot.onrender.com/webhook"
        asyncio.run(application.bot.set_webhook(webhook_url))
        logger.info(f"🔗 Webhook registered successfully: {webhook_url}")
    except Exception as e:
        logger.error(f"⚠️ Failed to register webhook automatically: {e}")

# ──────────────────────────────
# Start (for local debugging)
# ──────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Running locally on port {port}")
    app.run(host="0.0.0.0", port=port)






