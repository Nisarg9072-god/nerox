from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status

from app.db.mongodb import get_database

ORGANIZATIONS_COL = "organizations"
USAGE_COL = "usage"
API_KEYS_COL = "api_keys"
USERS_COL = "users"

PLAN_FREE = "free"
PLAN_PRO = "pro"
PLAN_ENTERPRISE = "enterprise"
ROLE_OWNER = "owner"
ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"

PLAN_LIMITS: dict[str, dict[str, int | None]] = {
    PLAN_FREE: {"scans": 50, "uploads": 100},
    PLAN_PRO: {"scans": 1000, "uploads": 5000},
    PLAN_ENTERPRISE: {"scans": None, "uploads": None},
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_plan_limits(plan: str) -> dict[str, int | None]:
    return PLAN_LIMITS.get(plan, PLAN_LIMITS[PLAN_FREE]).copy()


async def create_default_organization_for_user(
    *,
    user_id: ObjectId,
    company_name: str,
    plan: str = PLAN_FREE,
) -> ObjectId:
    db = get_database()
    now = utc_now()
    org_doc = {
        "name": company_name or "Default Organization",
        "owner_user_id": str(user_id),
        "plan": plan if plan in PLAN_LIMITS else PLAN_FREE,
        "created_at": now,
    }
    org_res = await db[ORGANIZATIONS_COL].insert_one(org_doc)
    org_id = org_res.inserted_id

    await db[USAGE_COL].update_one(
        {"organization_id": str(org_id)},
        {"$setOnInsert": {"organization_id": str(org_id), "scans_used": 0, "uploads_used": 0, "last_reset": now}},
        upsert=True,
    )
    await db[USERS_COL].update_one(
        {"_id": user_id},
        {"$set": {"organization_id": str(org_id), "role": ROLE_OWNER, "updated_at": now}},
    )
    return org_id


async def ensure_user_has_organization(user_doc: dict[str, Any]) -> dict[str, Any]:
    if user_doc.get("organization_id") and user_doc.get("role"):
        return user_doc
    uid = user_doc["_id"]
    org_id = await create_default_organization_for_user(
        user_id=uid,
        company_name=user_doc.get("company_name", "Default Organization"),
    )
    user_doc["organization_id"] = str(org_id)
    user_doc["role"] = ROLE_OWNER
    return user_doc


async def get_organization_for_user(user_doc: dict[str, Any]) -> dict[str, Any]:
    db = get_database()
    org_id = user_doc.get("organization_id")
    if not org_id:
        user_doc = await ensure_user_has_organization(user_doc)
        org_id = user_doc["organization_id"]
    org = await db[ORGANIZATIONS_COL].find_one({"_id": ObjectId(org_id)})
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


async def get_or_create_usage(organization_id: str) -> dict[str, Any]:
    db = get_database()
    usage = await db[USAGE_COL].find_one({"organization_id": organization_id})
    if usage:
        return usage
    now = utc_now()
    await db[USAGE_COL].insert_one(
        {"organization_id": organization_id, "scans_used": 0, "uploads_used": 0, "last_reset": now}
    )
    return {"organization_id": organization_id, "scans_used": 0, "uploads_used": 0, "last_reset": now}


async def enforce_scan_limit(organization_id: str, plan: str) -> None:
    usage = await get_or_create_usage(organization_id)
    limits = get_plan_limits(plan)
    scan_limit = limits.get("scans")
    if scan_limit is not None and int(usage.get("scans_used", 0)) >= int(scan_limit):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Scan limit reached")


async def enforce_upload_limit(organization_id: str, plan: str) -> None:
    usage = await get_or_create_usage(organization_id)
    limits = get_plan_limits(plan)
    upload_limit = limits.get("uploads")
    if upload_limit is not None and int(usage.get("uploads_used", 0)) >= int(upload_limit):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload limit reached")


async def increment_usage(organization_id: str, *, scans: int = 0, uploads: int = 0) -> None:
    db = get_database()
    inc_doc: dict[str, int] = {}
    if scans:
        inc_doc["scans_used"] = scans
    if uploads:
        inc_doc["uploads_used"] = uploads
    if not inc_doc:
        return
    await db[USAGE_COL].update_one(
        {"organization_id": organization_id},
        {"$inc": inc_doc, "$set": {"last_reset": utc_now()}},
        upsert=True,
    )


def generate_api_key() -> str:
    return f"nx_{secrets.token_urlsafe(32)}"
