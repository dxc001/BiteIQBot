import asyncio
import logging
import os

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
    global _bootstrapped
    if _bootstrapped:
        return

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        _db.check_connection()
        logger.info("✅ Supabase connection established")
    except Exception as exc:  # pragma: no cover - startup failure should bubble
        logger.exception("❌ Supabase connection failed: %s", exc)
        raise

    try:
        asyncio.run(_telegram_bot.initialize())
        logger.info("🤖 Telegram bot initialized successfully")
    except Exception as exc:  # pragma: no cover
        logger.exception("❌ Telegram init failed: %s", exc)
        raise

    try:
        _scheduler.start()
        logger.info("🕒 Scheduler started")
    except Exception as exc:  # pragma: no cover
        logger.exception("❌ Scheduler failed: %s", exc)
        raise

    logger.info("🌐 Flask server ready (gunicorn app:app)")
    _bootstrapped = True


_bootstrap_once()


@app.get("/")
def index():
    return jsonify({"status": "ok", "service": "BiteIQBot"})


@app.post("/webhook")
def telegram_webhook():
    data = request.get_json(force=True)
    asyncio.run(_telegram_bot.process_update_json(data))
    return jsonify({"ok": True})


@app.post("/stripe-webhook")
def stripe_webhook():
    payload = request.data
    signature = request.headers.get("Stripe-Signature", "")
    return _stripe_handler.handle_webhook_event(payload, signature)


if __name__ == "__main__":
    _bootstrap_once()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
