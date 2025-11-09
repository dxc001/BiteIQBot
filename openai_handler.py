from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL
from database import SupabaseDB
from typing import List, Dict, Any, Optional
import json
import re

class OpenAIHandler:
    def __init__(self, db: SupabaseDB):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.db = db
        self.model = OPENAI_MODEL

    def call_openai(self, messages: List[Dict[str, str]], max_tokens=500, temperature=0.6) -> str:
        """Base method for calling OpenAI API"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error: {str(e)}"

    def generate_plan_json(self, profile: dict, day_label: str, avoid_titles: List[str]) -> dict:
        """Generate a meal plan in JSON format based on user profile"""
        extra = ""
        if day_label.lower() == "tomorrow":
            extra = "Make tomorrow's plan different from today's meals while keeping nutrition similar."
        if avoid_titles:
            extra += f" Avoid these recent meals: {', '.join(avoid_titles)}."

        prompt = (
            "You are a concise nutrition coach. Return ONLY valid JSON, no markdown. "
            "Keys: meals(list), total_calories(int), tip(string). "
            "Each meal item: meal('Breakfast'/'Lunch'/'Dinner' or 'Snack'), title, description, calories(int). "
            "Keep descriptions short (<20 words). "
            f"PROFILE: {profile}. DAY: {day_label}. Include Breakfast, Lunch, Dinner (one Snack optional). {extra}"
        )

        raw = self.call_openai([{"role": "user", "content": prompt}], max_tokens=600, temperature=0.6)

        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.DOTALL)

        try:
            data = json.loads(raw)
            if "meals" in data:
                return data
        except Exception:
            pass

        return {
            "meals": [
                {"meal": "Breakfast", "title": "Greek Yogurt Bowl", "description": "Yogurt, berries, nuts.", "calories": 380},
                {"meal": "Lunch", "title": "Chicken Salad", "description": "Chicken, greens, olive oil.", "calories": 500},
                {"meal": "Dinner", "title": "Salmon & Quinoa", "description": "Salmon, quinoa, veg.", "calories": 620},
            ],
            "total_calories": 1500,
            "tip": "Drink water before meals."
        }

    def generate_recipe_text(self, meal_title: str, profile: Optional[dict]) -> str:
        """Generate a recipe for a specific meal"""
        profile_line = ""
        if profile:
            profile_line = (f"User: {profile.get('name', '')}, Age {profile.get('age', '')}, "
                           f"Diet {profile.get('diet', '')}. ")

        prompt = (
            "Write a short healthy recipe with EXACTLY these sections and labels:\n"
            "Ingredients:\n"
            "Steps:\n"
            "Tip:\n"
            "Under 120 words total. No extra commentary.\n"
            f"{profile_line}Meal: {meal_title}"
        )

        return self.call_openai([{"role": "user", "content": prompt}], max_tokens=350, temperature=0.55)

    def get_ai_response(self, telegram_id: int, user_message: str) -> str:
        """Get a response to a user's nutrition question"""
        user = self.db.get_user(telegram_id)

        prompt = (
            "You are a concise nutrition coach. Answer in <= 60 words. "
            "Only respond to nutrition/meal related questions."
        )

        try:
            response = self.call_openai([
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_message}
            ], max_tokens=160, temperature=0.5)

            return response
        except Exception as e:
            return "I'm having trouble processing your request. Please try again."

    def generate_meal_plan(self, telegram_id: int, preferences: str = "") -> str:
        """Generate a meal plan for display (backward compatibility)"""
        user = self.db.get_user(telegram_id)
        if not user:
            return "Please set up your profile first."

        profile = {
            "name": user.get("name", ""),
            "age": user.get("age", ""),
            "gender": user.get("gender", ""),
            "height_cm": user.get("height_cm", ""),
            "weight_kg": user.get("weight_kg", ""),
            "activity": user.get("activity", ""),
            "diet": user.get("diet", ""),
            "goal_kg": user.get("goal_kg", "")
        }

        recent = self.db.get_recent_meals(telegram_id, 7)
        plan = self.generate_plan_json(profile, "tomorrow", recent)

        result = f"**Tomorrow's Meal Plan**\n\n"
        for meal in plan.get("meals", []):
            result += f"**{meal.get('meal')}**: {meal.get('title')}\n"
            result += f"{meal.get('description')}\n"
            result += f"Calories: {meal.get('calories')}\n\n"

        result += f"**Total**: {plan.get('total_calories')} kcal\n"
        result += f"**Tip**: {plan.get('tip')}"

        return result

    def get_quick_tip(self) -> str:
        """Generate a quick health tip"""
        try:
            response = self.call_openai([
                {"role": "user", "content": "Give me one quick, actionable nutrition or health tip. Keep it under 50 words."}
            ], max_tokens=100, temperature=0.9)

            return response
        except Exception as e:
            return "Stay hydrated! Aim to drink at least 8 glasses of water throughout the day."
