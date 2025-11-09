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
# Stripe webhook endpointimport os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram_bot import TelegramBot
from database import SupabaseDB
from stripe_handler import StripeHandler
from openai_handler import OpenAIHandler
from scheduler import Scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = Flask(__name__)

# Initialize core services
db = SupabaseDB()
stripe_handler = StripeHandler(db)
openai_handler = OpenAIHandler(db)
bot = TelegramBot(db, openai_handler, stripe_handler)
scheduler = Scheduler(db)

@app.route("/", methods=["GET"])
def home():
    return "🤖 BiteIQBot is alive!", 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """Receive updates from Telegram"""
    try:
        update = request.get_json(force=True)
        logger.info(f"📩 Incoming Telegram update: {update}")

        async def process():
            await bot.process_update(update)

        try:
            asyncio.run(process())
        except RuntimeError:
            loop = asyncio.get_event_loop()
            loop.create_task(process())

        return "OK", 200
    except Exception as e:
        logger.exception(f"❌ Webhook error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe events"""
    try:
        payload = request.data
        sig_header = request.headers.get("Stripe-Signature")
        result = stripe_handler.handle_webhook(payload, sig_header)
        return jsonify(result), 200
    except Exception as e:
        logger.exception(f"❌ Stripe webhook error: {e}")
        return jsonify({"error": str(e)}), 500


def init_bot():
    """Startup sequence"""
    try:
        logger.info("🚀 Initializing BiteIQBot...")
        db.connect()
        scheduler.start()
        asyncio.run(bot.init_webhook())  # Registers webhook with Telegram
        logger.info("✅ Bot initialized successfully")
    except Exception as e:
        logger.exception(f"❌ Bot initialization failed: {e}")


if __name__ == "__main__":
    init_bot()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))







