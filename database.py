from supabase import create_client, Client
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
import json
import logging

# 🧩 Patch for Supabase + httpx proxy bug
import httpx
_original_client_init = httpx.Client.__init__
def _safe_init(self, *args, **kwargs):
    # remove invalid 'proxy' argument that some supabase/gotrue versions still pass
    kwargs.pop("proxy", None)
    return _original_client_init(self, *args, **kwargs)
httpx.Client.__init__ = _safe_init

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError(
                "❌ Supabase configuration missing. Please set SUPABASE_URL and SUPABASE_SERVICE_KEY in Render environment."
            )
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        logger.info("✅ Connected to Supabase successfully")


    # ------------------ User Management ------------------ #
def get_or_create_user(self, telegram_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
    """Retrieve user or create a new one if missing."""
    try:
        response = (
            self.client.table('users')
            .select('*')
            .eq('telegram_id', telegram_id)
            .maybe_single()
            .execute()
        )

        # 🧠 Defensive check — Supabase may return None if 406 or empty
        if not response or not getattr(response, "data", None):
            logger.warning(f"⚠️ No user found for telegram_id={telegram_id}, creating one...")
            new_user = {
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name,
                'created_at': datetime.now().isoformat(),
                'last_active': datetime.now().isoformat()
            }
            insert_response = self.client.table('users').insert(new_user).execute()
            logger.info(f"✅ Created new user for Telegram ID {telegram_id}")
            return insert_response.data[0] if insert_response and insert_response.data else new_user

        # ✅ User exists — update last_active timestamp
        self.client.table('users').update({
            'last_active': datetime.now().isoformat()
        }).eq('telegram_id', telegram_id).execute()

        return response.data

    except Exception as e:
        logger.error(f"❌ Error in get_or_create_user: {e}")
        return {}


    # ------------------ Profile ------------------ #
    def upsert_user_profile(self, telegram_id: int, name: str, age: int, gender: str,
                            height_cm: float, weight_kg: float, activity: str,
                            diet: str, goal_kg: float) -> None:
        """Insert or update user profile data."""
        profile_data = {
            'name': name,
            'age': age,
            'gender': gender,
            'height_cm': height_cm,
            'weight_kg': weight_kg,
            'activity': activity,
            'diet': diet,
            'goal_kg': goal_kg,
            'last_active': datetime.now().isoformat()
        }

        user = self.get_user(telegram_id)
        if user:
            self.client.table('users').update(profile_data).eq('telegram_id', telegram_id).execute()
        else:
            profile_data['telegram_id'] = telegram_id
            self.client.table('users').insert(profile_data).execute()

    # ------------------ Reminders ------------------ #
    def set_reminders(self, telegram_id: int, enabled: bool) -> None:
        """Enable or disable reminders for a user."""
        self.client.table('users').update({'reminders': enabled}).eq('telegram_id', telegram_id).execute()

    def get_users_with_reminders(self) -> List[int]:
        """Get Telegram IDs of all users with reminders enabled."""
        response = self.client.table('users').select('telegram_id').eq('reminders', True).execute()
        return [user['telegram_id'] for user in (response.data or [])]

    # ------------------ Subscriptions ------------------ #
    def has_active_subscription(self, telegram_id: int) -> bool:
        """Check if user has an active subscription."""
        response = self.client.rpc('has_active_subscription', {'user_telegram_id': telegram_id}).execute()
        return bool(response.data)

    def set_subscription(self, telegram_id: int, is_active: bool,
                         customer_id: str = None, sub_id: str = None) -> None:
        """Set or deactivate a subscription."""
        user = self.get_user(telegram_id)
        if not user:
            return

        if is_active and customer_id and sub_id:
            existing = self.client.table('subscriptions').select('*').eq('user_id', user['id']).maybe_single().execute()
            subscription_data = {
                'user_id': user['id'],
                'stripe_customer_id': customer_id,
                'stripe_subscription_id': sub_id,
                'status': 'active',
                'updated_at': datetime.now().isoformat()
            }
            if existing.data:
                self.client.table('subscriptions').update(subscription_data).eq('user_id', user['id']).execute()
            else:
                self.client.table('subscriptions').insert(subscription_data).execute()
        else:
            self.client.table('subscriptions').update({
                'status': 'inactive',
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user['id']).execute()

    def update_subscription_status(self, stripe_subscription_id: str,
                                   status: str, current_period_end: datetime = None) -> None:
        """Update subscription status by Stripe ID."""
        update_data = {'status': status, 'updated_at': datetime.now().isoformat()}
        if current_period_end:
            update_data['current_period_end'] = current_period_end.isoformat()
        self.client.table('subscriptions').update(update_data).eq('stripe_subscription_id', stripe_subscription_id).execute()

    # ------------------ Meal Plans ------------------ #
    def save_plan(self, telegram_id: int, plan_date: date, plan_json: dict) -> None:
        """Save or update a user's daily meal plan."""
        user = self.get_user(telegram_id)
        if not user:
            return

        plan_data = {
            'user_id': user['id'],
            'plan_date': plan_date.isoformat(),
            'plan_json': json.dumps(plan_json),
            'updated_at': datetime.now().isoformat()
        }

        self.client.table('plans').upsert(plan_data).execute()

    def get_plan(self, telegram_id: int, plan_date: date) -> Optional[dict]:
        """Retrieve a meal plan for a specific date."""
        user = self.get_user(telegram_id)
        if not user:
            return None

        response = self.client.table('plans').select('plan_json').eq(
            'user_id', user['id']
        ).eq('plan_date', plan_date.isoformat()).maybe_single().execute()

        if response.data:
            plan = response.data['plan_json']
            return json.loads(plan) if isinstance(plan, str) else plan
        return None

    # ------------------ Meal History ------------------ #
    def add_meals_to_history(self, telegram_id: int, meal_titles: List[str]) -> None:
        """Record meals to avoid repetition."""
        user = self.get_user(telegram_id)
        if not user or not meal_titles:
            return

        today = date.today().isoformat()
        meal_records = [{'user_id': user['id'], 'meal_title': m, 'seen_on': today} for m in meal_titles if m]
        if meal_records:
            self.client.table('meal_history').insert(meal_records).execute()

    def get_recent_meals(self, telegram_id: int, days: int = 7) -> List[str]:
        """Retrieve recent meals (to prevent duplication)."""
        user = self.get_user(telegram_id)
        if not user:
            return []

        cutoff_date = (date.today() - timedelta(days=days)).isoformat()
        response = self.client.table('meal_history').select('meal_title').eq(
            'user_id', user['id']
        ).gte('seen_on', cutoff_date).execute()

        return list({m['meal_title'] for m in (response.data or [])})

    # ------------------ Conversations ------------------ #
    def get_conversation_history(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Retrieve user's last conversation context."""
        user = self.get_user(telegram_id)
        if not user:
            return None

        response = self.client.table('conversation_history').select('*').eq(
            'user_id', user['id']
        ).order('updated_at', desc=True).limit(1).maybe_single().execute()
        return response.data

    def save_conversation_message(self, telegram_id: int, role: str, content: str) -> None:
        """Append a message to the conversation history."""
        user = self.get_user(telegram_id)
        if not user:
            return

        existing = self.get_conversation_history(telegram_id)
        now = datetime.now().isoformat()

        if existing:
            messages = existing.get('messages', [])
            messages.append({'role': role, 'content': content, 'timestamp': now})
            self.client.table('conversation_history').update({
                'messages': messages[-20:],  # keep last 20 messages
                'updated_at': now
            }).eq('id', existing['id']).execute()
        else:
            self.client.table('conversation_history').insert({
                'user_id': user['id'],
                'messages': [{'role': role, 'content': content, 'timestamp': now}],
                'updated_at': now
            }).execute()

