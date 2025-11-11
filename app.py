import asyncio
import logging
import os
import threading
from flask import Flask, jsonify, request
from telegram import Update

from database import SupabaseDB
from openai_handler import OpenAIHandler
from scheduler import Scheduler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_db = SupabaseDB()
_openai_handler = OpenAIHandler(_db)
_stripe_handler = StripeHandler(_db)
_telegram_bot = TelegramBot(_db, _openai_handler, _stripe_handler)
_scheduler = Scheduler(_db, _openai_handler, _telegram_bot)


def background_startup():
    """Start Telegram bot and scheduler in background."""
    try:
        asyncio.run(_telegram_bot.initialize())
        logger.info("🤖 Telegram bot initialized successfully")
    except Exception as exc:
        logger.exception("❌ Telegram init failed: %s", exc)

    try:
        _scheduler.start()
        logger.info("🕒 Scheduler started successfully")
    except Exception as exc:
        logger.exception("❌ Scheduler failed: %s", exc)


# --- ROUTES ---
@app.route("/", methods=["GET"])
def index():
    """Health check for Render + manual check."""
    if not any(t.name == "startup-thread" for t in threading.enumerate()):
        logger.info("🚀 Launching background services lazily...")
        threading.Thread(target=background_startup, daemon=True, name="startup-thread").start()

    return jsonify({
        "status": "ok",
        "service": "BiteIQBot",
        "message": "running on Render",
    }), 200


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    """Handle Telegram webhook."""
    data = request.get_json(force=True)

    try:
        update = Update.de_json(data, _telegram_bot.application.bot)

        # ✅ Safe async dispatch
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_telegram_bot.application.process_update(update))
        else:
            asyncio.run(_telegram_bot.application.process_update(update))

        logger.info(f"✅ Processed Telegram update: {update.effective_message.text if update.effective_message else 'no message'}")
        return jsonify({"ok": True}), 200

    except Exception as e:
        logger.exception("❌ Telegram webhook error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook."""
    payload = request.data
    signature = request.headers.get("Stripe-Signature", "")
    return _stripe_handler.handle_webhook_event(payload, signature)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🌍 Starting Flask app on port {port}")
    threading.Thread(target=background_startup, daemon=True, name="startup-thread").start()
    app.run(host="0.0.0.0", port=port)
