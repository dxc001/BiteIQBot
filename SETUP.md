# BiteIQBot Setup Guide

Complete setup instructions for deploying your Telegram AI diet assistant bot on Bolt.ai.

## Prerequisites

Before starting, you need to obtain the following:

### 1. Telegram Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` command
3. Follow the prompts to name your bot
4. Copy the bot token (format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
5. Send `/setcommands` to BotFather and set these commands:
   ```
   start - Start the bot
   menu - Show main menu
   help - Get help
   ```

### 2. OpenAI API Key

1. Go to [OpenAI API Keys](https://platform.openai.com/api-keys)
2. Sign in or create an account
3. Click "Create new secret key"
4. Copy the key (format: `sk-...`)
5. Make sure you have credits available in your account

### 3. Stripe Configuration

1. Go to [Stripe Dashboard](https://dashboard.stripe.com)
2. Sign in or create an account
3. Navigate to **Developers > API Keys**
4. Copy your **Secret key** (format: `sk_test_...` or `sk_live_...`)
5. Navigate to **Products** and create a subscription product
6. Copy the **Price ID** (format: `price_...`)
7. Navigate to **Developers > Webhooks**
8. Click **Add endpoint**
9. Set the endpoint URL to: `https://your-app.bolt.ai/stripe-webhook`
10. Select these events:
    - `checkout.session.completed`
    - `customer.subscription.updated`
    - `customer.subscription.deleted`
    - `invoice.payment_failed`
11. Copy the **Signing secret** (format: `whsec_...`)

### 4. Supabase Service Key

1. Go to your Supabase project dashboard
2. Navigate to **Settings > API**
3. Copy the **service_role key** (NOT the anon key)
4. This key has elevated permissions needed for the bot to manage data

### 5. Webhook URL

Your Bolt.ai deployment URL will be in the format:
```
https://your-app-name.bolt.ai
```

You'll need to update this after deployment.

## Configuration Steps

### Step 1: Update Environment Variables

Edit the `.env` file and replace all placeholder values:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
OPENAI_API_KEY=sk-proj-...your-key...
STRIPE_SECRET_KEY=sk_test_...your-key...
STRIPE_WEBHOOK_SECRET=whsec_...your-secret...
STRIPE_PRICE_ID=price_...your-price-id...
SUPABASE_SERVICE_KEY=your-service-role-key-here
WEBHOOK_URL=https://your-app.bolt.ai
```

### Step 2: Register Telegram Webhook

After deployment, the bot will automatically register its webhook with Telegram. The webhook URL will be:
```
https://your-app.bolt.ai/webhook
```

You can verify webhook setup by running:
```bash
curl https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo
```

### Step 3: Configure Stripe Webhook

1. Go to Stripe Dashboard > Developers > Webhooks
2. Update the endpoint URL to: `https://your-app.bolt.ai/stripe-webhook`
3. Ensure these events are selected:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
   - `invoice.payment_failed`

## Database Schema

The database is already set up with these tables:

- **users** - Stores Telegram user information
- **subscriptions** - Manages Stripe subscription data and status
- **reminders** - Stores user reminder preferences
- **conversation_history** - Maintains conversation context for AI responses

## Testing Your Bot

1. Search for your bot on Telegram using the username you set
2. Send `/start` command
3. You should see the welcome message and menu
4. Try the "Buy Subscription" option to test payment flow
5. After subscribing, test the AI features

## Available Endpoints

- `GET /` - Health check and bot info
- `GET /health` - Service health status
- `POST /webhook` - Telegram webhook (set automatically)
- `POST /stripe-webhook` - Stripe webhook (configure in Stripe dashboard)
- `GET /payment-success` - Payment confirmation page
- `GET /payment-cancelled` - Payment cancellation page

## Bot Features

### Main Menu Options

1. **Ask a Question** - Get AI-powered nutrition advice
2. **Get Tomorrow's Plan** - Generate personalized meal plan
3. **Manage Reminders** - Set up daily health reminders
4. **Buy Subscription** - Subscribe to unlock all features
5. **Help** - View help and commands

### Access Control

- Most features require an active subscription
- Subscription status is checked before processing premium commands
- Payment verification happens automatically via Stripe webhooks

### Reminders

When activated, users receive:
- Daily health tip at 9:00 AM
- Water reminder at 12:00 PM
- Additional reminders can be customized

## Troubleshooting

### Bot doesn't respond
- Check that TELEGRAM_BOT_TOKEN is correct
- Verify webhook is set correctly with `/getWebhookInfo`
- Check application logs for errors

### Payment doesn't activate features
- Verify STRIPE_WEBHOOK_SECRET is correct
- Check Stripe webhook events are being received
- Look for webhook errors in Stripe dashboard

### AI responses fail
- Ensure OPENAI_API_KEY is valid
- Check you have available credits in OpenAI account
- Review application logs for OpenAI errors

### Database errors
- Verify SUPABASE_SERVICE_KEY is correct
- Check that database tables were created successfully
- Ensure Row Level Security policies allow service role access

## Security Notes

- Never commit the `.env` file with real credentials
- Use environment variables for all sensitive data
- The bot uses Supabase service role key for database access
- Stripe webhook signature verification is enabled
- All payment processing is handled securely by Stripe

## Support

For issues:
1. Check application logs
2. Verify all environment variables are set
3. Test each API key independently
4. Review Stripe and Telegram webhook logs

## Verification Checklist

After configuring the environment variables locally you can verify that the stack is healthy with the following commands:

```bash
python app.py
```

The startup log should include:

- `✅ Supabase connection established`
- `🤖 Telegram bot initialized successfully`
- `🕒 Scheduler started`
- `🌐 Flask server ready (gunicorn app:app)`

With the dev server still running in another terminal, run:

```bash
curl -s http://localhost:5000/
curl -s -X POST http://localhost:5000/webhook -H "Content-Type: application/json" -d '{}'
curl -s -X POST http://localhost:5000/stripe-webhook -H "Content-Type: application/json" -d '{}'
```

Each command should return an HTTP 200 response. For production validation, Render will invoke:

```bash
gunicorn app:app --bind 0.0.0.0:8000
```

Ensure no errors are printed during that startup phase.
