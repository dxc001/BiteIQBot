import stripe
from config import STRIPE_SECRET_KEY, STRIPE_PRICE_ID, WEBHOOK_URL
from database import Database
from datetime import datetime
from typing import Dict, Any

stripe.api_key = STRIPE_SECRET_KEY

class StripeHandler:
    def __init__(self, db: Database):
        self.db = db

    def create_checkout_session(self, telegram_id: int) -> str:
        user = self.db.get_or_create_user(telegram_id)

        try:
            checkout_session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price': STRIPE_PRICE_ID,
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f'{WEBHOOK_URL}/payment-success?session_id={{CHECKOUT_SESSION_ID}}',
                cancel_url=f'{WEBHOOK_URL}/payment-cancelled',
                client_reference_id=str(telegram_id),
                metadata={
                    'telegram_id': str(telegram_id)
                }
            )
            return checkout_session.url
        except Exception as e:
            raise Exception(f"Failed to create checkout session: {str(e)}")

    def handle_checkout_completed(self, session: Dict[str, Any]) -> None:
        telegram_id = int(session.get('client_reference_id') or session.get('metadata', {}).get('telegram_id'))

        subscription_id = session.get('subscription')
        customer_id = session.get('customer')

        if subscription_id:
            subscription = stripe.Subscription.retrieve(subscription_id)
            period_end = datetime.fromtimestamp(subscription.current_period_end)

            self.db.create_subscription(
                telegram_id=telegram_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                status=subscription.status,
                current_period_end=period_end
            )

    def handle_subscription_updated(self, subscription: Dict[str, Any]) -> None:
        subscription_id = subscription['id']
        status = subscription['status']
        period_end = datetime.fromtimestamp(subscription['current_period_end'])

        self.db.update_subscription_status(
            stripe_subscription_id=subscription_id,
            status=status,
            current_period_end=period_end
        )

    def handle_subscription_deleted(self, subscription: Dict[str, Any]) -> None:
        subscription_id = subscription['id']
        self.db.update_subscription_status(
            stripe_subscription_id=subscription_id,
            status='cancelled'
        )

    def handle_invoice_payment_failed(self, invoice: Dict[str, Any]) -> None:
        subscription_id = invoice.get('subscription')
        if subscription_id:
            self.db.update_subscription_status(
                stripe_subscription_id=subscription_id,
                status='past_due'
            )

    def handle_webhook_event(self, payload: bytes, signature: str) -> Dict[str, Any]:
        from config import STRIPE_WEBHOOK_SECRET

        try:
            event = stripe.Webhook.construct_event(
                payload, signature, STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            raise ValueError("Invalid payload")
        except stripe.error.SignatureVerificationError:
            raise ValueError("Invalid signature")

        event_type = event['type']
        data = event['data']['object']

        if event_type == 'checkout.session.completed':
            self.handle_checkout_completed(data)
        elif event_type == 'customer.subscription.updated':
            self.handle_subscription_updated(data)
        elif event_type == 'customer.subscription.deleted':
            self.handle_subscription_deleted(data)
        elif event_type == 'invoice.payment_failed':
            self.handle_invoice_payment_failed(data)

        return {'status': 'success', 'event_type': event_type}
