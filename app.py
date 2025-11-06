import asyncio
import logging
from flask import Flask, request, jsonify
from telegram_bot import TelegramBot
from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from config import WEBHOOK_URL, TELEGRAM_BOT_TOKEN

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# Initialize your core components
db = Database()
openai_handler = OpenAIHandler()
stripe_handler = StripeHandler()

# Initialize Telegram bot
bot = TelegramBot(db=db, openai_handler=openai_handler, stripe_handler=stripe_handler)
application = bot.application


@app.before_first_request
def setup():
    """Set the Telegram webhook when the service starts."""
    import requests

    try:
        webhook_url = f"{WEBHOOK_URL}/webhook"
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook",
            params={"url": webhook_url},
            timeout=10,
        )
        logger.info(f"🤖 Webhook set: {resp.text}")
    except Exception as e:
        logger.exception(f"❌ Failed to set webhook: {e}")


@app.route("/")
def index():
    return "BiteIQBot is live!", 200


@app.post("/webhook")
def webhook():
    """Handle Telegram webhook updates."""
    try:
        update_data = request.get_json(force=True)
        if not update_data:
            return jsonify({"error": "No update data"}), 400

        logger.info(f"📩 Incoming update: {update_data}")

        async def process():
            await application.process_update(
                application.update_queue.factory.update_from_dict(update_data)
            )

        # ✅ SAFE ASYNC LOOP FIX
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If the loop is already running, schedule task
            loop.create_task(process())
        else:
            # If not running (Render case), start a clean event loop
            asyncio.run(process())

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


if __name__ == "__main__":
    import os

    port = int(os.environ.get("PORT", 8080))
    logger.info(f"🚀 Starting BiteIQBot server on port {port}")
    app.run(host="0.0.0.0", port=port)



