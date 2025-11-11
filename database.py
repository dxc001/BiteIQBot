import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
from supabase import Client, create_client

SUPABASE_URL = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

_logger = logging.getLogger(__name__)


# Render occasionally injects a proxy argument that breaks httpx; guard against it.
_original_httpx_client_init = httpx.Client.__init__


def _safe_httpx_init(self, *args, **kwargs):
    kwargs.pop("proxy", None)
    return _original_httpx_client_init(self, *args, **kwargs)


httpx.Client.__init__ = _safe_httpx_init


class SupabaseDB:
    def __init__(self) -> None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise ValueError(
                "SUPABASE_URL/VITE_SUPABASE_URL and SUPABASE_SERVICE_KEY must be set."
            )

        self.client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------
    def check_connection(self) -> None:
        self.client.table("users").select("id").limit(1).execute()

    # ------------------------------------------------------------------
    # User helpers
    # ------------------------------------------------------------------
    def get_or_create_user(
        self, telegram_id: int, username: Optional[str] = None
    ) -> Dict[str, Any]:
        user = self.get_user(telegram_id)
        if user:
            return user
        return self.create_user(telegram_id, username)

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        response = (
            self.client.table("users")
            .select("*")
            .eq("telegram_id", telegram_id)
            .maybe_single()
            .execute()
        )
        return response.data if getattr(response, "data", None) else None

    def create_user(
        self, telegram_id: int, username: Optional[str] = None
    ) -> Dict[str, Any]:
        payload = {
            "telegram_id": telegram_id,
            "username": username,
            "created_at": datetime.utcnow().isoformat(),
            "last_active": datetime.utcnow().isoformat(),
        }
        response = self.client.table("users").insert(payload).execute()
        return response.data[0] if getattr(response, "data", None) else payload

    def update_user(self, telegram_id: int, **fields: Any) -> None:
        if not fields:
            return
        fields["last_active"] = datetime.utcnow().isoformat()
        self.client.table("users").update(fields).eq("telegram_id", telegram_id).execute()

    def get_all_users(self) -> List[Dict[str, Any]]:
        response = self.client.table("users").select("*").execute()
        return response.data or []

    # ------------------------------------------------------------------
    # Meal plans / history
    # ------------------------------------------------------------------
    def save_plan(self, telegram_id: int, day_label: str, plan_json: Dict[str, Any]) -> None:
        user = self.get_user(telegram_id)
        if not user:
            return

        payload = {
            "user_id": user.get("id"),
            "plan_day_label": day_label,
            "plan_json": json.dumps(plan_json),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.client.table("plans").upsert(payload).execute()

    def get_recent_meals(self, telegram_id: int, limit: int = 10) -> List[str]:
        user = self.get_user(telegram_id)
        if not user:
            return []

        response = (
            self.client.table("meal_history")
            .select("meal_title")
            .eq("user_id", user.get("id"))
            .order("seen_on", desc=True)
            .limit(limit)
            .execute()
        )
        titles = [row.get("meal_title") for row in (response.data or []) if row.get("meal_title")]
        # dedupe while preserving order
        seen: List[str] = []
        for title in titles:
            if title not in seen:
                seen.append(title)
        return seen

    def add_meals_to_history(self, telegram_id: int, meals: List[str]) -> None:
        user = self.get_user(telegram_id)
        if not user or not meals:
            return

        rows = [
            {
                "user_id": user.get("id"),
                "meal_title": title,
                "seen_on": datetime.utcnow().date().isoformat(),
            }
            for title in meals
            if title
        ]
        if rows:
            self.client.table("meal_history").insert(rows).execute()

    # ------------------------------------------------------------------
    # Subscription helpers
    # ------------------------------------------------------------------
    def has_active_subscription(self, telegram_id: int) -> bool:
        user = self.get_user(telegram_id)
        if not user:
            return False

        response = (
            self.client.table("subscriptions")
            .select("status")
            .eq("user_id", user.get("id"))
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        return bool(response.data)

    def create_subscription(
        self,
        telegram_id: int,
        customer_id: str,
        sub_id: str,
        price_id: str,
        status: str,
    ) -> None:
        user = self.get_or_create_user(telegram_id)
        payload = {
            "user_id": user.get("id"),
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": sub_id,
            "stripe_price_id": price_id,
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.client.table("subscriptions").upsert(payload, on_conflict="stripe_subscription_id").execute()

    def update_subscription_status(self, subscription_id: str, status: str) -> None:
        self.client.table("subscriptions").update(
            {"status": status, "updated_at": datetime.utcnow().isoformat()}
        ).eq("stripe_subscription_id", subscription_id).execute()

    # ------------------------------------------------------------------
    # Conversation helpers (legacy compatibility)
    # ------------------------------------------------------------------
    def get_conversation_history(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        user = self.get_user(telegram_id)
        if not user:
            return None

        response = (
            self.client.table("conversation_history")
            .select("*")
            .eq("user_id", user.get("id"))
            .order("updated_at", desc=True)
            .limit(1)
            .maybe_single()
            .execute()
        )
        return response.data if getattr(response, "data", None) else None

    def save_conversation_message(self, telegram_id: int, role: str, content: str) -> None:
        user = self.get_user(telegram_id)
        if not user:
            return

        history = self.get_conversation_history(telegram_id)
        now = datetime.utcnow().isoformat()
        if history:
            messages = history.get("messages", [])
            messages.append({"role": role, "content": content, "timestamp": now})
            self.client.table("conversation_history").update(
                {"messages": messages[-20:], "updated_at": now}
            ).eq("id", history["id"]).execute()
        else:
            self.client.table("conversation_history").insert(
                {
                    "user_id": user.get("id"),
                    "messages": [{"role": role, "content": content, "timestamp": now}],
                    "updated_at": now,
                }
            ).execute()


Database = SupabaseDB
