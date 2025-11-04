/*
  # Fix Security Issues
  
  1. Function Security
    - Add explicit search_path to functions to prevent search path manipulation attacks
    - Set search_path to 'public' for security
  
  2. Note on Indexes
    - Indexes are marked as unused because no queries have been run yet
    - These indexes are correctly defined and will be used by the application
    - They optimize queries by user_id, telegram_id, dates, and foreign keys
    - Keeping indexes as they are essential for performance when app is in use
*/

-- Drop existing functions
DROP FUNCTION IF EXISTS has_active_subscription(bigint);
DROP FUNCTION IF EXISTS update_user_last_active(bigint);

-- Recreate has_active_subscription function with secure search_path
CREATE OR REPLACE FUNCTION has_active_subscription(user_telegram_id bigint)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
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

-- Recreate update_user_last_active function with secure search_path
CREATE OR REPLACE FUNCTION update_user_last_active(user_telegram_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE users
  SET last_active = now()
  WHERE telegram_id = user_telegram_id;
END;
$$;