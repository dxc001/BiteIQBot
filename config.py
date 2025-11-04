import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID', 'price_default')

SUPABASE_URL = os.getenv('VITE_SUPABASE_URL')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.bolt.ai')

PORT = int(os.getenv('PORT', 8080))
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
