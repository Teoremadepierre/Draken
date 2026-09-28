"""User management and invitations."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from draken.api.deps import current_user
from draken.core.config import settings
from draken.core.database import get_db
from draken.core.models import UserRole
from draken.services import accounts

router = APIRouter(prefix="/api/users", tags=["users"])


class InviteRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=120)
    email: str = ""
    display_name: str = ""
    role: str = UserRole.editor.value
    valid_days: int = Field(14, ge=1, le=90)
    project_ids: list[int] = Field(default_factory=list)


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8)


class UpdateUserRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None
    display_name: str | None = None
    email: str | None = None
    ai_engine: str | None = None
    ai_api_key: str | None = None


def _out(user) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "last_login_at": user.last_login_at,
        "has_password": bool(user.password_hash),
        "pending_invite": bool(user.invite_token),
        # Never return the key itself, only whether one is set.
        "has_own_ai_key": bool(user.ai_api_key),
        "ai_engine": user.ai_engine,
    }


@router.get("")
def list_users(db: Session = Depends(get_db), _user: str = Depends(current_user)):
    accounts.ensure_bootstrap_owner(db)
    return [_out(u) for u in accounts.list_users(db)]


@router.get("/me")
def me(db: Session = Depends(get_db), username: str = Depends(current_user)):
    user = accounts.get_user(db, username)
    if user is None:
        return {
            "username": username,
            "role": UserRole.owner.value if not settings.auth_enabled else UserRole.editor.value,
            "auth_enabled": settings.auth_enabled,
            "is_bootstrap": True,
        }
    return {**_out(user), "auth_enabled": settings.auth_enabled}


@router.post("/invite", status_code=201)
def invite(
    payload: InviteRequest,
    db: Session = Depends(get_db),
    username: str = Depends(current_user),
):
    """Create an inactive user and a one-time link they use to set a password.

    No email is sent: you pass the link along however you like, so adding a
    colleague never depends on SMTP being configured.
    """
    try:
        return accounts.invite_user(
            db,
            username=payload.username,
            email=payload.email,
            display_name=payload.display_name,
            role=payload.role,
            invited_by=username,
            valid_days=payload.valid_days,
            project_ids=payload.project_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/accept-invite")
def accept_invite(payload: AcceptInviteRequest, db: Session = Depends(get_db)):
    """Public: exchange an invite token for an active account."""
    try:
        user = accounts.accept_invite(db, token=payload.token, password=payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="This invite is not valid or has expired")

    from draken.core.security import issue_token

    return {
        "ok": True,
        "username": user.username,
        "token": issue_token(user.username),
        "role": user.role,
    }


@router.patch("/{user_id}")
def update_user(
    user_id: int,
    payload: UpdateUserRequest,
    db: Session = Depends(get_db),
    _username: str = Depends(current_user),
):
    try:
        user = accounts.update_user(db, user_id=user_id, **payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return _out(user)


@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    _username: str = Depends(current_user),
):
    try:
        ok = accounts.delete_user(db, user_id=user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail="User not found")
