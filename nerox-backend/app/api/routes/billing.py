from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from bson import ObjectId

from app.core.dependencies import get_current_user, get_current_user_with_role
from app.db.mongodb import get_database
from app.services.billing_service import create_checkout_session, handle_webhook
from app.services.saas_service import ROLE_ADMIN, ROLE_OWNER

router = APIRouter()


class CheckoutRequest(BaseModel):
    plan: str = Field(pattern="^(pro|enterprise)$")


@router.get("/test")
async def billing_test() -> dict:
    return {"status": "ok", "service": "billing"}


@router.post("/checkout")
async def checkout(
    body: CheckoutRequest,
    current_user: dict = Depends(get_current_user_with_role(ROLE_OWNER, ROLE_ADMIN)),
) -> dict:
    db = get_database()
    org = await db["organizations"].find_one({"_id": ObjectId(current_user["organization_id"])})
    result = await create_checkout_session(body.plan, org, current_user)
    return {"plan": body.plan, **result}


@router.post("/webhook")
async def billing_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict:
    payload = await request.body()
    return await handle_webhook(payload, stripe_signature)
