import logging
import os
import asyncio
from flask import Flask, request, jsonify
from telegram import Update

from database import SupabaseDB
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = Flask(__name__)

# --- Instantiate bot components ---
db = SupabaseDB()
openai_handler = OpenAIHandler()
stripe_handler = StripeHandler()
telegram_bot = TelegramBot(db, openai_handler, stripe_handler)

# --- Initialize Telegram bot once ---
@app.before_first_request
def init_bot():
    asyncio.run(telegram_bot.initialize())


@app.route("/", methods=["GET"])
def index():
    return jsonify({"message": "running on Render", "service": "BiteIQBot", "status": "ok"}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle Telegram webhook updates."""
    try:
        data = request.get_json(force=True)
        logger.info(f"📩 Incoming Telegram update: {data}")

        update = Update.de_json(data, telegram_bot.application.bot)
        asyncio.run(telegram_bot.application.process_update(update))

        logger.info("✅ Processed Telegram update successfully")
        return jsonify({"ok": True}), 200
    except Exception as e:
        logger.exception("❌ Telegram webhook error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))


