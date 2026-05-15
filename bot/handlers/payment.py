import logging

import stripe
from aiohttp import web
from aiogram import Bot
from sqlalchemy import select

from bot.db.models import Subscription
from bot.db.session import AsyncSessionLocal
from bot.services.billing import activate_subscription
from bot.utils.config import settings

logger = logging.getLogger(__name__)


def stripe_webhook_handler(bot: Bot):
    """Returns an aiohttp request handler bound to the given Bot instance."""

    async def handler(request: web.Request) -> web.Response:
        payload = await request.read()
        sig = request.headers.get("stripe-signature", "")

        try:
            event = stripe.Webhook.construct_event(
                payload, sig, settings.stripe_webhook_secret
            )
        except stripe.SignatureVerificationError:
            logger.warning("Invalid Stripe webhook signature")
            return web.Response(status=400, text="Invalid signature")
        except Exception:
            logger.exception("Stripe webhook parse error")
            return web.Response(status=400, text="Bad request")

        event_type = event["type"]
        logger.info("Stripe event: %s", event_type)

        if event_type == "checkout.session.completed":
            obj = event["data"]["object"]
            try:
                user_id = int(obj["metadata"]["telegram_user_id"])
            except (KeyError, ValueError):
                logger.error("Missing telegram_user_id in checkout metadata")
                return web.Response(status=200)
            stripe_sub_id = obj.get("subscription") or ""
            stripe_customer_id = obj.get("customer") or ""

            async with AsyncSessionLocal() as session:
                await activate_subscription(session, user_id, stripe_sub_id, stripe_customer_id)

            await _notify_user(bot, user_id)

        elif event_type == "invoice.payment_succeeded":
            invoice = event["data"]["object"]
            stripe_sub_id = invoice.get("subscription") or ""
            stripe_customer_id = invoice.get("customer") or ""

            # Look up user_id via stored customer_id
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Subscription)
                    .where(Subscription.stripe_customer_id == stripe_customer_id)
                    .limit(1)
                )
                sub = result.scalar_one_or_none()
                if sub is None:
                    logger.warning("No subscription found for customer %s", stripe_customer_id)
                    return web.Response(status=200)
                user_id = sub.user_id
                await activate_subscription(session, user_id, stripe_sub_id, stripe_customer_id)

            await _notify_user(bot, user_id)

        return web.Response(status=200)

    return handler


async def _notify_user(bot: Bot, user_id: int) -> None:
    try:
        await bot.send_message(user_id, "✅ Payment confirmed. Your knowledge base is active!")
    except Exception:
        logger.warning("Could not notify user %s (may have blocked the bot)", user_id)


def create_checkout_url(user_id: int) -> str:
    checkout = stripe.checkout.Session.create(
        api_key=settings.stripe_secret_key,
        mode="subscription",
        line_items=[{"price": settings.stripe_price_id, "quantity": 1}],
        success_url="https://t.me/your_bot",
        cancel_url="https://t.me/your_bot",
        metadata={"telegram_user_id": str(user_id)},
    )
    return checkout.url
