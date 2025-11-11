import json
import logging
from typing import Any, Dict, List, Optional

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL
from database import SupabaseDB

_logger = logging.getLogger(__name__)


class OpenAIHandler:
    def __init__(self, db: SupabaseDB):
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be configured.")

        self.db = db
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL or "gpt-4o-mini"

    def _call_chat_completion(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 600,
        temperature: float = 0.6,
    ) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content.strip()

    def generate_plan_json(
        self,
        profile: Dict[str, Any],
        day_label: str,
        avoid_titles: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        avoid_titles = avoid_titles or []
        prompt = (
            "You are a concise nutrition coach. Return ONLY valid JSON, no markdown. "
            "Keys: meals(list), total_calories(int), tip(string). "
            "Each meal item: meal('Breakfast'/'Lunch'/'Dinner' or 'Snack'), title, description, calories(int). "
            "Keep descriptions under 20 words."
        )

        extras: List[str] = []
        if day_label:
            extras.append(f"Plan is for {day_label}.")
        if avoid_titles:
            extras.append(f"Avoid repeating meals titled: {', '.join(avoid_titles)}.")

        prompt += " " + " ".join(extras)
        prompt += f" PROFILE: {json.dumps(profile)}"

        try:
            raw = self._call_chat_completion(
                [{"role": "user", "content": prompt}],
                max_tokens=700,
                temperature=0.6,
            )
            cleaned = raw.strip().strip("`")
            data = json.loads(cleaned)
            if "meals" in data:
                return data
        except Exception as exc:
            _logger.exception("OpenAI meal plan generation failed: %s", exc)

        return {
            "meals": [
                {
                    "meal": "Breakfast",
                    "title": "Oatmeal with Berries",
                    "description": "Rolled oats with almond milk, berries, and seeds.",
                    "calories": 380,
                },
                {
                    "meal": "Lunch",
                    "title": "Grilled Chicken Salad",
                    "description": "Chicken, leafy greens, quinoa, vinaigrette.",
                    "calories": 520,
                },
                {
                    "meal": "Dinner",
                    "title": "Salmon and Veggies",
                    "description": "Baked salmon with roasted vegetables and brown rice.",
                    "calories": 610,
                },
            ],
            "total_calories": 1510,
            "tip": "Remember to sip water throughout the day.",
        }

    def generate_recipe_text(self, meal_title: str, profile: Optional[Dict[str, Any]]) -> str:
        context = ""
        if profile:
            context = json.dumps(profile)

        try:
            return self._call_chat_completion(
                [
                    {
                        "role": "user",
                        "content": (
                            "Write a short healthy recipe with EXACTLY these sections and labels:\n"
                            "Ingredients:\nSteps:\nTip:\n"
                            "Under 120 words total."
                            f" Profile: {context}. Meal: {meal_title}"
                        ),
                    }
                ],
                max_tokens=350,
                temperature=0.55,
            )
        except Exception as exc:  # pragma: no cover
            _logger.exception("OpenAI recipe generation failed: %s", exc)
            return "Try a balanced plate with lean protein, vegetables, and whole grains."

    def get_ai_response(self, telegram_id: int, user_message: str) -> str:
        _ = self.db.get_user(telegram_id)
        try:
            return self._call_chat_completion(
                [
                    {
                        "role": "system",
                        "content": "You are a concise nutrition coach. Answer in <= 60 words.",
                    },
                    {"role": "user", "content": user_message},
                ],
                max_tokens=160,
                temperature=0.5,
            )
        except Exception as exc:  # pragma: no cover
            _logger.exception("OpenAI chat response failed: %s", exc)
            return "I'm having trouble right now—please try again later."


__all__ = ["OpenAIHandler"]
