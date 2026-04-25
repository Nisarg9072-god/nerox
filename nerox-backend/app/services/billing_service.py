from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import stripe
from bson import ObjectId
from fastapi import HTTPException, status

from app.core.config import settings
from app.db.mongodb import get_database

ORGS_COL = "organizations"
USERS_COL = "users"
BILLING_EVENTS_COL = "billing_events"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stripe_client() -> None:
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Billing is not configured")
    stripe.api_key = settings.STRIPE_SECRET_KEY


def _price_for_plan(plan: str) -> str | None:
    plan = plan.lower().strip()
    if plan == "pro":
        return settings.STRIPE_PRICE_PRO_MONTHLY
    if plan == "enterprise":
        return settings.STRIPE_PRICE_ENTERPRISE_MONTHLY
    return None


async def create_checkout_session(plan: str, organization: dict[str, Any], user: dict[str, Any]) -> dict[str, str]:
    plan = plan.lower().strip()
    if plan == "free":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Free plan does not require checkout")

    price_id = _price_for_plan(plan)
    if not price_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported plan '{plan}'")

    _stripe_client()
    customer_id = organization.get("stripe_customer_id")
    if not customer_id:
        customer = stripe.Customer.create(
            email=user.get("email"),
            name=user.get("company_name") or user.get("name") or "Nerox Customer",
            metadata={"organization_id": str(organization["_id"]), "user_id": str(user["_id"])},
        )
        customer_id = customer["id"]
        db = get_database()
        await db[ORGS_COL].update_one(
            {"_id": organization["_id"]},
            {"$set": {"stripe_customer_id": customer_id, "updated_at": _utc_now()}},
        )

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        success_url=settings.STRIPE_SUCCESS_URL,
        cancel_url=settings.STRIPE_CANCEL_URL,
        line_items=[{"price": price_id, "quantity": 1}],
        metadata={"organization_id": str(organization["_id"]), "plan": plan, "user_id": str(user["_id"])},
    )
    return {"checkout_url": session.url, "session_id": session.id}


async def upgrade_plan(user_id: str, plan: str) -> None:
    db = get_database()
    user = await db[USERS_COL].find_one({"_id": ObjectId(user_id)})
    if not user:
        return
    org_id = user.get("organization_id")
    if not org_id:
        return
    await db[ORGS_COL].update_one(
        {"_id": ObjectId(org_id)},
        {"$set": {"plan": plan, "plan_status": "active", "updated_at": _utc_now()}},
    )


async def handle_webhook(payload: bytes, signature: str | None) -> dict[str, Any]:
    _stripe_client()
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stripe webhook is not configured")
    if not signature:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing Stripe signature")

    event = stripe.Webhook.construct_event(payload=payload, sig_header=signature, secret=settings.STRIPE_WEBHOOK_SECRET)
    db = get_database()
    existing = await db[BILLING_EVENTS_COL].find_one({"event_id": event.get("id")})
    if existing:
        return {"status": "duplicate", "event_id": event.get("id")}

    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})
    if event_type == "checkout.session.completed":
        metadata = data.get("metadata", {}) or {}
        org_id = metadata.get("organization_id")
        plan = metadata.get("plan", "pro")
        subscription_id = data.get("subscription")
        customer_id = data.get("customer")
        if org_id:
            await db[ORGS_COL].update_one(
                {"_id": ObjectId(org_id)},
                {
                    "$set": {
                        "plan": plan,
                        "plan_status": "active",
                        "stripe_customer_id": customer_id,
                        "stripe_subscription_id": subscription_id,
                        "updated_at": _utc_now(),
                    }
                },
            )
    elif event_type == "customer.subscription.deleted":
        subscription_id = data.get("id")
        if subscription_id:
            await db[ORGS_COL].update_one(
                {"stripe_subscription_id": subscription_id},
                {"$set": {"plan_status": "canceled", "updated_at": _utc_now()}},
            )

    await db[BILLING_EVENTS_COL].insert_one(
        {"event_id": event.get("id"), "type": event_type, "processed_at": _utc_now()}
    )
    return {"status": "processed", "event_id": event.get("id"), "type": event_type}
