"""Users, project membership and read-only share links.

Deliberately small. This is an internal tool for a team, so the model is: a few
named users with three roles, optional per-project membership, and tokenised
read-only links for people who should see a report without getting an account.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from draken.core.config import settings
from draken.core.logging import get_logger
from draken.core.models import (
    ActivityLog,
    Project,
    ProjectMember,
    ShareLink,
    ShareScope,
    User,
    UserRole,
    utcnow,
)
from draken.core.security import hash_password, verify_password

log = get_logger(__name__)

ROLE_RANK = {UserRole.viewer.value: 0, UserRole.editor.value: 1, UserRole.owner.value: 2}


def _token() -> str:
    return secrets.token_urlsafe(24)


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------


def ensure_bootstrap_owner(db: Session) -> User | None:
    """Make the .env admin a real user row so ownership has a subject.

    Without this, a deployment that only ever used DRAKEN_ADMIN_* has no user to
    attribute actions to and no way to invite anyone.
    """
    if not settings.admin_user:
        return None
    existing = db.execute(
        select(User).where(User.username == settings.admin_user)
    ).scalars().first()
    if existing is not None:
        return existing

    owner = User(
        username=settings.admin_user,
        display_name=settings.admin_user,
        password_hash=settings.admin_password_hash or "",
        role=UserRole.owner.value,
        is_active=True,
    )
    db.add(owner)
    db.commit()
    log.info("created bootstrap owner user %r", owner.username)
    return owner


def list_users(db: Session) -> list[User]:
    return list(db.execute(select(User).order_by(User.id)).scalars())


def get_user(db: Session, username: str) -> User | None:
    return db.execute(select(User).where(User.username == username)).scalars().first()


def authenticate(db: Session, *, username: str, password: str) -> User | None:
    """Check a user row first, then fall back to the .env admin credentials."""
    user = get_user(db, username)
    if user and user.is_active and user.password_hash:
        if verify_password(password, user.password_hash):
            user.last_login_at = utcnow()
            db.commit()
            return user
        return None

    if (
        username == settings.admin_user
        and settings.admin_password_hash
        and verify_password(password, settings.admin_password_hash)
    ):
        owner = ensure_bootstrap_owner(db)
        if owner:
            owner.last_login_at = utcnow()
            db.commit()
        return owner
    return None


def invite_user(
    db: Session,
    *,
    username: str,
    email: str = "",
    display_name: str = "",
    role: str = UserRole.editor.value,
    invited_by: str = "",
    valid_days: int = 14,
    project_ids: list[int] | None = None,
) -> dict:
    """Create an inactive user plus a one-time invite link.

    No email is sent: the operator passes the link along however they like, which
    avoids making SMTP a hard dependency for adding a colleague.
    """
    if role not in ROLE_RANK:
        raise ValueError(f"invalid role {role!r}; expected one of {sorted(ROLE_RANK)}")
    if get_user(db, username):
        raise ValueError(f"user {username!r} already exists")

    token = _token()
    user = User(
        username=username,
        email=email,
        display_name=display_name or username,
        role=role,
        is_active=False,                       # activates when they set a password
        invite_token=token,
        invite_expires_at=datetime.now(UTC) + timedelta(days=valid_days),
    )
    db.add(user)
    db.flush()

    for project_id in project_ids or []:
        db.add(ProjectMember(project_id=project_id, user_id=user.id, role=role))

    db.add(
        ActivityLog(
            actor=invited_by or "system",
            action="user.invited",
            entity_type="user",
            entity_id=user.id,
            detail={"username": username, "role": role, "projects": project_ids or []},
        )
    )
    db.commit()

    return {
        "user_id": user.id,
        "username": username,
        "role": role,
        "invite_path": f"/invite/{token}",
        "expires_at": user.invite_expires_at,
        "note": (
            "Send this path to the person. Opening it lets them set a password and sign in. "
            "It works once and then stops."
        ),
    }


def accept_invite(db: Session, *, token: str, password: str) -> User | None:
    user = db.execute(select(User).where(User.invite_token == token)).scalars().first()
    if user is None or not token:
        return None
    expires = user.invite_expires_at
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            return None
    if len(password) < 8:
        raise ValueError("password must be at least 8 characters")

    user.password_hash = hash_password(password)
    user.is_active = True
    user.invite_token = ""
    user.invite_expires_at = None
    db.commit()
    log.info("invite accepted by %r", user.username)
    return user


def update_user(
    db: Session,
    *,
    user_id: int,
    role: str | None = None,
    is_active: bool | None = None,
    display_name: str | None = None,
    email: str | None = None,
    ai_engine: str | None = None,
    ai_api_key: str | None = None,
) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None
    if role is not None:
        if role not in ROLE_RANK:
            raise ValueError(f"invalid role {role!r}")
        user.role = role
    if is_active is not None:
        user.is_active = is_active
    if display_name is not None:
        user.display_name = display_name
    if email is not None:
        user.email = email
    if ai_engine is not None:
        user.ai_engine = ai_engine
    if ai_api_key is not None:
        user.ai_api_key = ai_api_key
    db.commit()
    return user


def delete_user(db: Session, *, user_id: int) -> bool:
    user = db.get(User, user_id)
    if user is None:
        return False
    owners = db.execute(
        select(User).where(User.role == UserRole.owner.value, User.is_active.is_(True))
    ).scalars().all()
    if user.role == UserRole.owner.value and len(owners) <= 1:
        raise ValueError("cannot delete the only owner")
    db.delete(user)
    db.commit()
    return True


def visible_projects(db: Session, *, user: User | None) -> list[Project]:
    """Owners see everything; others see what they are a member of."""
    if user is None or user.role == UserRole.owner.value:
        return list(db.execute(select(Project).order_by(Project.id)).scalars())
    project_ids = [
        m.project_id
        for m in db.execute(
            select(ProjectMember).where(ProjectMember.user_id == user.id)
        ).scalars()
    ]
    if not project_ids:
        # No explicit membership: show everything rather than an empty tool.
        # Restriction is opt-in, which suits a small internal team.
        return list(db.execute(select(Project).order_by(Project.id)).scalars())
    return list(
        db.execute(select(Project).where(Project.id.in_(project_ids)).order_by(Project.id)).scalars()
    )


def can(user: User | None, action: str) -> bool:
    """Coarse permission check. ``action`` is 'read', 'write' or 'admin'."""
    if user is None:
        return True                              # auth disabled
    rank = ROLE_RANK.get(user.role, 0)
    return {"read": 0, "write": 1, "admin": 2}.get(action, 2) <= rank


# ---------------------------------------------------------------------------
# share links
# ---------------------------------------------------------------------------


def create_share_link(
    db: Session,
    *,
    project: Project,
    label: str = "",
    scope: str = ShareScope.report.value,
    created_by: str = "",
    valid_days: int | None = 30,
    allow_ai_brief: bool = True,
) -> ShareLink:
    link = ShareLink(
        project_id=project.id,
        token=_token(),
        label=label or f"{project.name} report",
        scope=scope,
        created_by=created_by,
        expires_at=(datetime.now(UTC) + timedelta(days=valid_days)) if valid_days else None,
        allow_ai_brief=allow_ai_brief,
    )
    db.add(link)
    db.add(
        ActivityLog(
            project_id=project.id,
            actor=created_by or "system",
            action="share.created",
            entity_type="share_link",
            detail={"scope": scope, "expires_days": valid_days, "label": link.label},
        )
    )
    db.commit()
    return link


def list_share_links(db: Session, *, project_id: int) -> list[ShareLink]:
    return list(
        db.execute(
            select(ShareLink)
            .where(ShareLink.project_id == project_id)
            .order_by(ShareLink.id.desc())
        ).scalars()
    )


def resolve_share_link(db: Session, *, token: str) -> tuple[ShareLink | None, Project | None]:
    link = db.execute(select(ShareLink).where(ShareLink.token == token)).scalars().first()
    if link is None or not link.is_valid:
        return None, None
    project = db.get(Project, link.project_id)
    link.view_count += 1
    link.last_viewed_at = utcnow()
    db.commit()
    return link, project


def revoke_share_link(db: Session, *, link_id: int) -> bool:
    link = db.get(ShareLink, link_id)
    if link is None:
        return False
    link.revoked = True
    db.commit()
    return True
