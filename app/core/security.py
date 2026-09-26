"""Session-authenticated identity and browser request protections."""
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models import UserSession
from app.services.auth_service import load_valid_session, verify_csrf


@dataclass(frozen=True)
class Principal:
    user_id: int


@dataclass(frozen=True)
class SessionPrincipal(Principal):
    """Server-derived identity plus the internal session row identifier."""

    session_id: int


def get_session_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionPrincipal:
    """Authenticate only from the configured opaque session cookie."""
    settings = get_settings()
    raw_token = request.cookies.get(settings.session_cookie_name)
    session = load_valid_session(db, raw_token, settings=settings)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return SessionPrincipal(user_id=session.user_id, session_id=session.id)


def get_current_principal(
    request: Request,
    db: Session = Depends(get_db),
) -> SessionPrincipal:
    """Canonical HTTP identity: a validated server-side session only."""
    return get_session_principal(request=request, db=db)


def require_allowed_origin(request: Request, settings: Settings) -> None:
    """Require an exact configured browser Origin for credential mutations."""
    origin = request.headers.get("origin", "").rstrip("/")
    if origin not in settings.frontend_allowed_origins:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def require_csrf_protection(
    request: Request,
    principal: SessionPrincipal = Depends(get_current_principal),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
) -> None:
    """Protect persistent cookie-authenticated mutations from CSRF."""
    settings = get_settings()
    require_allowed_origin(request, settings)
    session = db.scalar(
        select(UserSession).where(UserSession.id == principal.session_id)
    )
    if session is None or not verify_csrf(session, csrf_token):
        raise HTTPException(status_code=403, detail="CSRF validation failed")
