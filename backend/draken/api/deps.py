"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from draken.core.config import settings
from draken.core.database import get_db
from draken.core.models import Project
from draken.core.security import verify_token


def current_user(
    request: Request,
    authorization: str | None = Header(default=None),
) -> str:
    """Resolve the operator from a bearer token or the session cookie."""
    if not settings.auth_enabled:
        return "anonymous"

    token = ""
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        token = request.cookies.get("draken_session", "")
    username = verify_token(token) if token else None
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return username


def get_project(
    project_id: int,
    db: Session = Depends(get_db),
    _user: str = Depends(current_user),
) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project
