from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from app.core.dependencies import get_current_user, get_current_user_with_role
from app.db.mongodb import get_database
from app.services.saas_service import (
    ROLE_ADMIN,
    ROLE_MEMBER,
    ROLE_OWNER,
    generate_api_key,
    get_or_create_usage,
    get_organization_for_user,
    get_plan_limits,
)

router = APIRouter()


class UsageResponse(BaseModel):
    organization_id: str
    plan: str
    scans_used: int
    scans_limit: int | None
    uploads_used: int
    uploads_limit: int | None
    last_reset: datetime


class TeamUserItem(BaseModel):
    user_id: str
    email: str
    name: str = ""
    role: str


class TeamUsersResponse(BaseModel):
    organization_id: str
    users: list[TeamUserItem]


class AddUserToOrgRequest(BaseModel):
    email: EmailStr
    role: str = Field(default=ROLE_MEMBER)


class UpdateRoleRequest(BaseModel):
    role: str = Field(pattern="^(owner|admin|member)$")


@router.get("/usage", response_model=UsageResponse)
async def get_usage(current_user: dict = Depends(get_current_user)) -> UsageResponse:
    org = await get_organization_for_user(current_user)
    org_id = str(org["_id"])
    usage = await get_or_create_usage(org_id)
    limits = get_plan_limits(org.get("plan", "free"))
    return UsageResponse(
        organization_id=org_id,
        plan=org.get("plan", "free"),
        scans_used=int(usage.get("scans_used", 0)),
        scans_limit=limits.get("scans"),
        uploads_used=int(usage.get("uploads_used", 0)),
        uploads_limit=limits.get("uploads"),
        last_reset=usage.get("last_reset", datetime.now(timezone.utc)),
    )


@router.get("/users", response_model=TeamUsersResponse)
async def list_org_users(
    current_user: dict = Depends(get_current_user_with_role(ROLE_OWNER)),
) -> TeamUsersResponse:
    db = get_database()
    org_id = current_user.get("organization_id")
    rows = await db["users"].find({"organization_id": org_id}).to_list(length=500)
    return TeamUsersResponse(
        organization_id=org_id,
        users=[
            TeamUserItem(
                user_id=str(u["_id"]),
                email=u.get("email", ""),
                name=u.get("name", u.get("company_name", "")),
                role=u.get("role", ROLE_MEMBER),
            )
            for u in rows
        ],
    )


@router.post("/users/add", response_model=TeamUserItem)
async def add_user_to_org(
    body: AddUserToOrgRequest,
    current_user: dict = Depends(get_current_user_with_role(ROLE_OWNER)),
) -> TeamUserItem:
    db = get_database()
    target = await db["users"].find_one({"email": body.email.lower()})
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if body.role not in {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid role")
    await db["users"].update_one(
        {"_id": target["_id"]},
        {"$set": {"organization_id": current_user["organization_id"], "role": body.role}},
    )
    return TeamUserItem(
        user_id=str(target["_id"]),
        email=target.get("email", ""),
        name=target.get("name", target.get("company_name", "")),
        role=body.role,
    )


@router.patch("/users/{user_id}/role", response_model=TeamUserItem)
async def update_user_role(
    user_id: str,
    body: UpdateRoleRequest,
    current_user: dict = Depends(get_current_user_with_role(ROLE_OWNER)),
) -> TeamUserItem:
    db = get_database()
    try:
        oid = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user id")

    target = await db["users"].find_one({"_id": oid, "organization_id": current_user["organization_id"]})
    if not target:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db["users"].update_one({"_id": oid}, {"$set": {"role": body.role}})
    return TeamUserItem(
        user_id=str(target["_id"]),
        email=target.get("email", ""),
        name=target.get("name", target.get("company_name", "")),
        role=body.role,
    )


@router.post("/api-keys/create")
async def create_api_key(
    current_user: dict = Depends(get_current_user_with_role(ROLE_OWNER, ROLE_ADMIN)),
) -> dict:
    db = get_database()
    key = generate_api_key()
    now = datetime.now(timezone.utc)
    await db["api_keys"].insert_one(
        {
            "key": key,
            "organization_id": current_user["organization_id"],
            "created_at": now,
            "active": True,
        }
    )
    return {"key": key, "created_at": now.isoformat(), "active": True}
