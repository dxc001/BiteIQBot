import os
import logging
import asyncio
from flask import Flask, request, jsonify
from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# === Initialize components ===
app = Flask(__name__)
db = Database()
openai_handler = OpenAIHandler(db=db)
stripe_handler = StripeHandler(db=db)
bot = TelegramBot(db=db, openai_handler=openai_handler, stripe_handler=stripe_handler)


# === Async initialization workaround for Flask 3.x ===
# Flask 3.x removed before_first_request, so we run startup manually on first hit
bot_initialized = False

async def initialize_bot_once():
    global bot_initialized
    if not bot_initialized:
        await bot.initialize()
        bot_initialized = True
        logger.info("🤖 Bot initialized successfully")


@app.route("/", methods=["GET"])
def home():
    """Render health check"""
    return "✅ BiteIQBot is running on Render", 200


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Handle Telegram updates"""
    try:
        update_data = request.get_json(force=True)
        logger.info(f"📩 Incoming Telegram update: {update_data}")

        async def process():
            await initialize_bot_once()
            await bot.application.update_queue.put(update_data)

        try:
            asyncio.run(process())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.create_task(process())

        return "OK", 200

    except Exception as e:
        logger.exception(f"❌ Telegram webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe events."""
    try:
        event = request.get_json(force=True)
        logger.info(f"💳 Stripe event received: {event.get('type')}")
        # TODO: implement subscription updates later
        return "OK", 200
    except Exception as e:
        logger.exception(f"❌ Stripe webhook error: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    logger.info(f"🚀 Starting BiteIQBot server on port {port}")
    app.run(host="0.0.0.0", port=port)





