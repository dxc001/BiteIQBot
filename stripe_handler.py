from typing import Any, Dict

from flask import jsonify
import stripe

from config import STRIPE_PRICE_ID, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, WEBHOOK_URL
from database import SupabaseDB

stripe.api_key = STRIPE_SECRET_KEY


class StripeHandler:
    def __init__(self, db: SupabaseDB):
        if not STRIPE_SECRET_KEY:
            raise ValueError("STRIPE_SECRET_KEY must be configured.")
        if not STRIPE_WEBHOOK_SECRET:
            raise ValueError("STRIPE_WEBHOOK_SECRET must be configured.")
        self.db = db

    def create_checkout_session(self, telegram_id: int) -> str:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
            mode="subscription",
            success_url=f"{WEBHOOK_URL}/payment-success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{WEBHOOK_URL}/payment-cancelled",
            client_reference_id=str(telegram_id),
            metadata={"telegram_id": str(telegram_id), "price_id": STRIPE_PRICE_ID},
        )
        return session.url

    def handle_webhook_event(self, payload: bytes, signature: str):  # Flask response tuple
        try:
            event = stripe.Webhook.construct_event(payload, signature, STRIPE_WEBHOOK_SECRET)
        except Exception as exc:  # pragma: no cover - handled via HTTP status
            return jsonify({"error": str(exc)}), 400

        event_type = event.get("type")
        data_object: Dict[str, Any] = event.get("data", {}).get("object", {})

        if event_type == "checkout.session.completed":
            telegram_id = int(
                data_object.get("client_reference_id")
                or data_object.get("metadata", {}).get("telegram_id", 0)
            )
            customer_id = data_object.get("customer")
            subscription_id = data_object.get("subscription")
            price_id = data_object.get("metadata", {}).get("price_id")
            status = data_object.get("status", "active")
            if telegram_id and customer_id and subscription_id:
                self.db.create_subscription(
                    telegram_id=telegram_id,
                    customer_id=customer_id,
                    sub_id=subscription_id,
                    price_id=price_id or "unknown",
                    status=status,
                )
        elif event_type in {"customer.subscription.updated", "customer.subscription.deleted"}:
            subscription_id = data_object.get("id")
            status = data_object.get("status", "canceled")
            if subscription_id:
                self.db.update_subscription_status(subscription_id, status)

        return jsonify({"status": "success"}), 200
