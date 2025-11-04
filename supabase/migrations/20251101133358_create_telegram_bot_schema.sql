/*
  # BiteIQBot Database Schema
  
  1. New Tables
    - `users`
      - `id` (uuid, primary key)
      - `telegram_id` (bigint, unique) - Telegram user ID
      - `username` (text) - Telegram username
      - `first_name` (text) - User's first name
      - `created_at` (timestamptz) - Account creation timestamp
      - `last_active` (timestamptz) - Last interaction timestamp
    
    - `subscriptions`
      - `id` (uuid, primary key)
      - `user_id` (uuid, foreign key to users)
      - `stripe_customer_id` (text, unique) - Stripe customer ID
      - `stripe_subscription_id` (text, unique) - Stripe subscription ID
      - `status` (text) - Subscription status: active, expired, cancelled, trialing
      - `current_period_end` (timestamptz) - When current period ends
      - `created_at` (timestamptz) - Subscription creation timestamp
      - `updated_at` (timestamptz) - Last update timestamp
    
    - `reminders`
      - `id` (uuid, primary key)
      - `user_id` (uuid, foreign key to users)
      - `reminder_type` (text) - Type of reminder: meal, water, exercise
      - `schedule_time` (text) - Cron-style schedule or time string
      - `is_active` (boolean) - Whether reminder is enabled
      - `created_at` (timestamptz) - Reminder creation timestamp
    
    - `conversation_history`
      - `id` (uuid, primary key)
      - `user_id` (uuid, foreign key to users)
      - `messages` (jsonb) - Array of conversation messages
      - `context` (jsonb) - Additional context data
      - `created_at` (timestamptz) - Conversation start timestamp
      - `updated_at` (timestamptz) - Last message timestamp
  
  2. Security
    - Enable RLS on all tables
    - Add policies for authenticated access (service role will be used by bot)
  
  3. Indexes
    - Index on telegram_id for fast user lookups
    - Index on stripe_customer_id and stripe_subscription_id for payment verification
    - Index on user_id for efficient queries across all tables
*/

-- Create users table
CREATE TABLE IF NOT EXISTS users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_id bigint UNIQUE NOT NULL,
  username text,
  first_name text,
  created_at timestamptz DEFAULT now(),
  last_active timestamptz DEFAULT now()
);

-- Create subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  stripe_customer_id text UNIQUE,
  stripe_subscription_id text UNIQUE,
  status text DEFAULT 'inactive' NOT NULL,
  current_period_end timestamptz,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Create reminders table
CREATE TABLE IF NOT EXISTS reminders (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  reminder_type text NOT NULL,
  schedule_time text NOT NULL,
  is_active boolean DEFAULT true,
  created_at timestamptz DEFAULT now()
);

-- Create conversation_history table
CREATE TABLE IF NOT EXISTS conversation_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  messages jsonb DEFAULT '[]'::jsonb,
  context jsonb DEFAULT '{}'::jsonb,
  created_at timestamptz DEFAULT now(),
  updated_at timestamptz DEFAULT now()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer ON subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription ON subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_reminders_user_id ON reminders(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_user_id ON conversation_history(user_id);

-- Enable Row Level Security
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversation_history ENABLE ROW LEVEL SECURITY;

-- Create policies for service role access (bot will use service role key)
CREATE POLICY "Service role can manage users"
  ON users FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Service role can manage subscriptions"
  ON subscriptions FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Service role can manage reminders"
  ON reminders FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Service role can manage conversation history"
  ON conversation_history FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

-- Create helper function to check if user has active subscription
CREATE OR REPLACE FUNCTION has_active_subscription(user_telegram_id bigint)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  active_sub boolean;
BEGIN
  SELECT EXISTS(
    SELECT 1
    FROM subscriptions s
    JOIN users u ON s.user_id = u.id
    WHERE u.telegram_id = user_telegram_id
      AND s.status IN ('active', 'trialing')
      AND (s.current_period_end IS NULL OR s.current_period_end > now())
  ) INTO active_sub;
  
  RETURN active_sub;
END;
$$;

-- Create function to update last_active timestamp
CREATE OR REPLACE FUNCTION update_user_last_active(user_telegram_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE users
  SET last_active = now()
  WHERE telegram_id = user_telegram_id;
END;
$$;
