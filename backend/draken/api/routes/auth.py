"""Login / session endpoints for the single-operator dashboard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from draken.core.config import settings
from draken.core.schemas import LoginRequest, TokenOut
from draken.core.security import issue_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status() -> dict:
    return {
        "auth_enabled": settings.auth_enabled,
        "configured": settings.has_admin_credentials if settings.auth_enabled else True,
        "hint": (
            "Set DRAKEN_ADMIN_PASSWORD, or generate a hash with "
            "`python -m draken.cli.main hash-password 'yourpassword'` and set "
            "DRAKEN_ADMIN_PASSWORD_HASH (preferred: the password itself never enters "
            "the environment)."
        ) if settings.auth_enabled and not settings.has_admin_credentials else "",
    }


@router.post("/login", response_model=TokenOut)
def login(payload: LoginRequest, response: Response) -> TokenOut:
    if not settings.auth_enabled:
        token = issue_token(payload.username or "anonymous")
        return TokenOut(token=token, username=payload.username or "anonymous",
                        expires_in_hours=settings.session_ttl_hours)
    if not settings.has_admin_credentials:
        raise HTTPException(
            status_code=503,
            detail=(
                "Auth is enabled but DRAKEN_ADMIN_PASSWORD_HASH is not set. Run "
                "`python -m draken.cli.main hash-password 'yourpassword'` and add the result to .env."
            ),
        )
    from draken.core.database import SessionLocal
    from draken.services import accounts

    db = SessionLocal()
    try:
        user = accounts.authenticate(db, username=payload.username, password=payload.password)
    finally:
        db.close()
    if user is None:
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
