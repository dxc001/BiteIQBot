# --- Gevent patch must be FIRST for Render compatibility ---
from gevent import monkey
monkey.patch_all()

# --- Standard imports ---
import asyncio
import logging
from flask import Flask, request, jsonify

# --- Internal modules ---
from database import Database
from openai_handler import OpenAIHandler
from stripe_handler import StripeHandler
from telegram_bot import TelegramBot
from scheduler import ReminderScheduler
from config import PORT, DEBUG, WEBHOOK_URL

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- Flask app setup ---
app = Flask(__name__)

# --- Initialize core components ---
db = Database()
openai_handler = OpenAIHandler(db)
stripe_handler = StripeHandler(db)
telegram_bot = TelegramBot(db, openai_handler, stripe_handler)
scheduler = ReminderScheduler(db, openai_handler)


# --- Bot initialization on startup ---
@app.before_request
def initialize_bot_once():
    if not hasattr(app, "_bot_initialized"):
        app._bot_initialized = True
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(telegram_bot.initialize())

            webhook_url = f"{WEBHOOK_URL}/webhook"
            loop.run_until_complete(
                telegram_bot.application.bot.set_webhook(webhook_url)
            )
            logger.info(f"✅ Telegram webhook set to: {webhook_url}")

            scheduler.start()
            logger.info("⏰ Reminder scheduler started")

        except Exception as e:
            logger.error(f"❌ Failed to initialize bot: {e}")



# --- Health & status endpoints ---
@app.route('/')
def index():
    return jsonify({
        'status': 'online',
        'bot': 'BiteIQBot',
        'version': '1.0.0'
    })


@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy'}), 200


# --- Telegram webhook endpoint ---
@app.post("/webhook")
def telegram_webhook():
    try:
        from telegram import Update
        update = Update.de_json(request.get_json(force=True), telegram_bot.application.bot)

        # Debug: show received update type
        logger.info(f"📩 Incoming update: {update.to_dict()}")

        # Run async handler safely
        asyncio.run(telegram_bot.application.process_update(update))
        return "OK", 200

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.error(f"❌ Error processing Telegram webhook: {e}\n{tb}")
        return "ERROR", 500



# --- Stripe webhook endpoint ---
@app.route('/stripe-webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    try:
        result = stripe_handler.handle_webhook_event(payload, sig_header)
        logger.info(f"✅ Stripe webhook processed: {result}")
        return jsonify(result), 200
    except ValueError as e:
        logger.error(f"Stripe webhook error: {e}")
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f"Unexpected error in Stripe webhook: {e}")
        return jsonify({'error': 'Internal server error'}), 500


# --- Payment success page ---
@app.route('/payment-success')
def payment_success():
    return """
    <html>
        <head>
            <title>Payment Successful</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    text-align: center;
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                }
                h1 { color: #4CAF50; margin-bottom: 20px; }
                p { color: #666; font-size: 18px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>✅ Payment Successful!</h1>
                <p>Thank you for subscribing to BiteIQ Premium!</p>
                <p>Return to Telegram to start using all features.</p>
            </div>
        </body>
    </html>
    """


# --- Payment cancelled page ---
@app.route('/payment-cancelled')
def payment_cancelled():
    return """
    <html>
        <head>
            <title>Payment Cancelled</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }
                .container {
                    text-align: center;
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                }
                h1 { color: #ff9800; margin-bottom: 20px; }
                p { color: #666; font-size: 18px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>⚠️ Payment Cancelled</h1>
                <p>Your payment was cancelled.</p>
                <p>Return to Telegram and try again when you're ready.</p>
            </div>
        </body>
    </html>
    """


# --- Start app ---
if __name__ == '__main__':
    import os
    PORT = int(os.environ.get("PORT", 8080))  # fallback for local runs
    DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

    logger.info("🚀 Starting BiteIQBot application...")
    logger.info(f"🌐 Running Flask server on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)


