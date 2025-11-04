/*
  # Add Profile and Meal Planning Tables
  
  1. Updates to Existing Tables
    - Add profile fields to `users` table:
      - `name` (text) - User's full name
      - `age` (int) - User's age
      - `gender` (text) - M/F
      - `height_cm` (real) - Height in centimeters
      - `weight_kg` (real) - Weight in kilograms
      - `activity` (text) - Activity level: low/medium/high
      - `diet` (text) - Dietary restrictions
      - `goal_kg` (real) - Goal weight in kilograms
      - `reminders` (boolean) - Whether user has reminders enabled
  
  2. New Tables
    - `meal_history`
      - `id` (uuid, primary key)
      - `user_id` (uuid, foreign key to users)
      - `meal_title` (text) - Title of the meal
      - `seen_on` (date) - Date meal was seen
      - `created_at` (timestamptz) - Record creation timestamp
    
    - `plans`
      - `user_id` (uuid, foreign key to users)
      - `plan_date` (date) - Date for the plan
      - `plan_json` (jsonb) - Complete plan data
      - `created_at` (timestamptz) - Plan creation timestamp
      - PRIMARY KEY (user_id, plan_date)
  
  3. Security
    - Enable RLS on new tables
    - Add policies for service role access
  
  4. Indexes
    - Index on meal_history (user_id, seen_on) for recent meals lookup
    - Index on plans (user_id, plan_date) for plan retrieval
*/

-- Add profile fields to users table
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'name'
  ) THEN
    ALTER TABLE users ADD COLUMN name text;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'age'
  ) THEN
    ALTER TABLE users ADD COLUMN age int;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'gender'
  ) THEN
    ALTER TABLE users ADD COLUMN gender text;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'height_cm'
  ) THEN
    ALTER TABLE users ADD COLUMN height_cm real;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'weight_kg'
  ) THEN
    ALTER TABLE users ADD COLUMN weight_kg real;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'activity'
  ) THEN
    ALTER TABLE users ADD COLUMN activity text;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'diet'
  ) THEN
    ALTER TABLE users ADD COLUMN diet text;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'goal_kg'
  ) THEN
    ALTER TABLE users ADD COLUMN goal_kg real;
  END IF;
  
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'users' AND column_name = 'reminders'
  ) THEN
    ALTER TABLE users ADD COLUMN reminders boolean DEFAULT false;
  END IF;
END $$;

-- Create meal_history table
CREATE TABLE IF NOT EXISTS meal_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  meal_title text NOT NULL,
  seen_on date DEFAULT CURRENT_DATE,
  created_at timestamptz DEFAULT now()
);

-- Create plans table
CREATE TABLE IF NOT EXISTS plans (
  user_id uuid REFERENCES users(id) ON DELETE CASCADE NOT NULL,
  plan_date date NOT NULL,
  plan_json jsonb NOT NULL,
  created_at timestamptz DEFAULT now(),
  PRIMARY KEY (user_id, plan_date)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_meal_history_user_date ON meal_history(user_id, seen_on DESC);
CREATE INDEX IF NOT EXISTS idx_plans_user_date ON plans(user_id, plan_date DESC);

-- Enable Row Level Security
ALTER TABLE meal_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE plans ENABLE ROW LEVEL SECURITY;

-- Create policies for service role access
CREATE POLICY "Service role can manage meal history"
  ON meal_history FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

CREATE POLICY "Service role can manage plans"
  ON plans FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);