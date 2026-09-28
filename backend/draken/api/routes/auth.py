"""Login / session endpoints for the single-operator dashboard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from draken.core.config import settings
from draken.core.schemas import LoginRequest, TokenOut
from draken.core.security import issue_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status() -> dict:
    return {
        "auth_enabled": settings.auth_enabled,
        "configured": bool(settings.admin_password_hash) if settings.auth_enabled else True,
        "hint": (
            "Generate a hash with: python -m draken.cli.main hash-password 'yourpassword' "
            "then set DRAKEN_ADMIN_PASSWORD_HASH."
        ) if settings.auth_enabled and not settings.admin_password_hash else "",
    }


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, response: Response) -> TokenOut:
    if not settings.auth_enabled:
        token = issue_token(payload.username or "anonymous")
        return TokenOut(token=token, username=payload.username or "anonymous",
                        expires_in_hours=settings.session_ttl_hours)
    if not settings.admin_password_hash:
        raise HTTPException(
            status_code=503,
            detail=(
                "Auth is enabled but DRAKEN_ADMIN_PASSWORD_HASH is not set. Run "
                "`python -m draken.cli.main hash-password 'yourpassword'` and add the result to .env."
            ),
        )
    if payload.username != settings.admin_user or not verify_password(
        payload.password, settings.admin_password_hash
    ):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = issue_token(payload.username)
    response.set_cookie(
        "draken_session",
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.is_production,
    )
    return TokenOut(token=token, username=payload.username, expires_in_hours=settings.session_ttl_hours)


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie("draken_session")
    return {"ok": True}
