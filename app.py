import asyncio
import logging
import os
import threading
from flask import Flask, jsonify, request

from database import SupabaseDB
from openai_handler import OpenAIHandler
from scheduler import Scheduler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot

app = Flask(__name__)

_db = SupabaseDB()
_openai_handler = OpenAIHandler(_db)
_stripe_handler = StripeHandler(_db)
_telegram_bot = TelegramBot(_db, _openai_handler, _stripe_handler)
_scheduler = Scheduler(_db, _openai_handler, _telegram_bot)

_bootstrapped = False


def _bootstrap_once() -> None:
    """Initialize subsystems only once per container start."""
    global _bootstrapped
    if _bootstrapped:
        return

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    # --- Supabase connection ---
    try:
        _db.check_connection()
        logger.info("✅ Supabase connection established")
    except Exception as exc:
        logger.exception("❌ Supabase connection failed: %s", exc)
        raise

    # --- Telegram bot webhook initialization ---
    try:
        # Make sure Telegram runs webhook mode, not polling
        asyncio.run(_telegram_bot.initialize(webhook_mode=True))
        logger.info("🤖 Telegram bot initialized successfully (webhook mode)")
    except Exception as exc:
        logger.exception("❌ Telegram init failed: %s", exc)
        raise

    # --- Scheduler in background thread ---
    try:
        threading.Thread(target=_scheduler.start, daemon=True).start()
        logger.info("🕒 Scheduler started in background thread")
    except Exception as exc:
        logger.exception("❌ Scheduler failed: %s", exc)
        raise

    logger.info("🌐 Flask server ready (gunicorn app:app)")
    _bootstrapped = True


# Bootstrap once when container loads
_bootstrap_once()


@app.get("/")
def index():
    """Health check for Render and browser."""
    return jsonify({"status": "ok", "service": "BiteIQBot", "webhook": True})


@app.post("/webhook")
def telegram_webhook():
    """Handle Telegram updates via webhook."""
    data = request.get_json(force=True)
    asyncio.run(_telegram_bot.process_update_json(data))
    return jsonify({"ok": True})


@app.post("/stripe-webhook")
def stripe_webhook():
    """Handle Stripe events."""
    payload = request.data
    signature = request.headers.get("Stripe-Signature", "")
    return _stripe_handler.handle_webhook_event(payload, signature)


if __name__ == "__main__":
    # Render expects port 8080, default fallback to 8080
    _bootstrap_once()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

