from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_KEY
from typing import Optional, Dict, Any, List
from datetime import datetime, date, timedelta
import json

class Database:
    def __init__(self):
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    def get_or_create_user(self, telegram_id: int, username: str = None, first_name: str = None) -> Dict[str, Any]:
        response = self.client.table('users').select('*').eq('telegram_id', telegram_id).maybe_single().execute()

        if response.data:
            self.client.table('users').update({
                'last_active': datetime.now().isoformat()
            }).eq('telegram_id', telegram_id).execute()
            return response.data
        else:
            new_user = {
                'telegram_id': telegram_id,
                'username': username,
                'first_name': first_name
            }
            response = self.client.table('users').insert(new_user).execute()
            return response.data[0]

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user profile by telegram_id"""
        response = self.client.table('users').select('*').eq('telegram_id', telegram_id).maybe_single().execute()
        return response.data

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users"""
        response = self.client.table('users').select('*').execute()
        return response.data

    def upsert_user_profile(self, telegram_id: int, name: str, age: int, gender: str,
                           height_cm: float, weight_kg: float, activity: str,
                           diet: str, goal_kg: float) -> None:
        """Update or insert user profile information"""
        user = self.get_user(telegram_id)

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

        if user:
            self.client.table('users').update(profile_data).eq('telegram_id', telegram_id).execute()
        else:
            profile_data['telegram_id'] = telegram_id
            self.client.table('users').insert(profile_data).execute()

    def set_reminders(self, telegram_id: int, enabled: bool) -> None:
        """Enable or disable reminders for a user"""
        self.client.table('users').update({
            'reminders': enabled
        }).eq('telegram_id', telegram_id).execute()

    def get_users_with_reminders(self) -> List[int]:
        """Get telegram_ids of all users with reminders enabled"""
        response = self.client.table('users').select('telegram_id').eq('reminders', True).execute()
        return [user['telegram_id'] for user in response.data]

    def has_active_subscription(self, telegram_id: int) -> bool:
        """Check if user has an active subscription"""
        response = self.client.rpc('has_active_subscription', {'user_telegram_id': telegram_id}).execute()
        return response.data if response.data is not None else False

    def set_subscription(self, telegram_id: int, is_active: bool,
                        customer_id: str = None, sub_id: str = None) -> None:
        """Update subscription status for a user"""
        user = self.get_user(telegram_id)
        if not user:
            return

        if is_active and customer_id and sub_id:
            # Check if subscription exists
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
            # Deactivate subscription
            self.client.table('subscriptions').update({
                'status': 'inactive',
                'updated_at': datetime.now().isoformat()
            }).eq('user_id', user['id']).execute()

    def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Alias for get_user"""
        return self.get_user(telegram_id)

    def create_subscription(self, telegram_id: int, stripe_customer_id: str,
                          stripe_subscription_id: str, status: str,
                          current_period_end: datetime) -> Dict[str, Any]:
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            raise ValueError(f"User with telegram_id {telegram_id} not found")

        subscription_data = {
            'user_id': user['id'],
            'stripe_customer_id': stripe_customer_id,
            'stripe_subscription_id': stripe_subscription_id,
            'status': status,
            'current_period_end': current_period_end.isoformat()
        }

        response = self.client.table('subscriptions').insert(subscription_data).execute()
        return response.data[0]

    def update_subscription_status(self, stripe_subscription_id: str,
                                  status: str, current_period_end: datetime = None) -> None:
        update_data = {
            'status': status,
            'updated_at': datetime.now().isoformat()
        }
        if current_period_end:
            update_data['current_period_end'] = current_period_end.isoformat()

        self.client.table('subscriptions').update(update_data).eq(
            'stripe_subscription_id', stripe_subscription_id
        ).execute()

    def get_subscription_by_stripe_id(self, stripe_subscription_id: str) -> Optional[Dict[str, Any]]:
        response = self.client.table('subscriptions').select(
            '*, users!inner(*)'
        ).eq('stripe_subscription_id', stripe_subscription_id).maybe_single().execute()
        return response.data

    def add_reminder(self, telegram_id: int, reminder_type: str, schedule_time: str) -> Dict[str, Any]:
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            raise ValueError(f"User with telegram_id {telegram_id} not found")

        reminder_data = {
            'user_id': user['id'],
            'reminder_type': reminder_type,
            'schedule_time': schedule_time,
            'is_active': True
        }

        response = self.client.table('reminders').insert(reminder_data).execute()
        return response.data[0]

    def get_user_reminders(self, telegram_id: int) -> List[Dict[str, Any]]:
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            return []

        response = self.client.table('reminders').select('*').eq(
            'user_id', user['id']
        ).eq('is_active', True).execute()
        return response.data

    def deactivate_user_reminders(self, telegram_id: int) -> None:
        user = self.get_user_by_telegram_id(telegram_id)
        if user:
            self.client.table('reminders').update({
                'is_active': False
            }).eq('user_id', user['id']).execute()

    def save_plan(self, telegram_id: int, plan_date: date, plan_json: dict) -> None:
        """Save or update a meal plan for a specific date"""
        user = self.get_user(telegram_id)
        if not user:
            return

        plan_data = {
            'user_id': user['id'],
            'plan_date': plan_date.isoformat(),
            'plan_json': json.dumps(plan_json)
        }

        # Upsert: insert or update if exists
        self.client.table('plans').upsert(plan_data).execute()

    def get_plan(self, telegram_id: int, plan_date: date) -> Optional[dict]:
        """Get meal plan for a specific date"""
        user = self.get_user(telegram_id)
        if not user:
            return None

        response = self.client.table('plans').select('plan_json').eq(
            'user_id', user['id']
        ).eq('plan_date', plan_date.isoformat()).maybe_single().execute()

        if response.data:
            return json.loads(response.data['plan_json']) if isinstance(response.data['plan_json'], str) else response.data['plan_json']
        return None

    def add_meals_to_history(self, telegram_id: int, meal_titles: List[str]) -> None:
        """Add meals to history to avoid repetition"""
        user = self.get_user(telegram_id)
        if not user or not meal_titles:
            return

        meal_records = []
        for title in meal_titles:
            if title:
                meal_records.append({
                    'user_id': user['id'],
                    'meal_title': title,
                    'seen_on': date.today().isoformat()
                })

        if meal_records:
            self.client.table('meal_history').insert(meal_records).execute()

    def get_recent_meals(self, telegram_id: int, days: int = 7) -> List[str]:
        """Get recent meal titles to avoid repetition"""
        user = self.get_user(telegram_id)
        if not user:
            return []

        cutoff_date = (date.today() - timedelta(days=days)).isoformat()
        response = self.client.table('meal_history').select('meal_title').eq(
            'user_id', user['id']
        ).gte('seen_on', cutoff_date).execute()

        return list(set(meal['meal_title'] for meal in response.data))

    def get_conversation_history(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            return None

        response = self.client.table('conversation_history').select('*').eq(
            'user_id', user['id']
        ).order('updated_at', desc=True).limit(1).maybe_single().execute()
        return response.data

    def save_conversation_message(self, telegram_id: int, role: str, content: str) -> None:
        user = self.get_user_by_telegram_id(telegram_id)
        if not user:
            return

        conversation = self.get_conversation_history(telegram_id)

        if conversation:
            messages = conversation.get('messages', [])
            messages.append({'role': role, 'content': content, 'timestamp': datetime.now().isoformat()})

            self.client.table('conversation_history').update({
                'messages': messages[-20:],
                'updated_at': datetime.now().isoformat()
            }).eq('id', conversation['id']).execute()
        else:
            self.client.table('conversation_history').insert({
                'user_id': user['id'],
                'messages': [{'role': role, 'content': content, 'timestamp': datetime.now().isoformat()}]
            }).execute()
