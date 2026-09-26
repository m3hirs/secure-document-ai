"""Password and opaque-session primitives for local authentication.

Raw passwords, session tokens, and CSRF tokens must never be persisted or
logged. Public HTTP behavior is implemented by ``app.api.auth``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets

from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.db.models import User, UserSession


_PASSWORD_HASH = PasswordHash.recommended()
# A fixed valid Argon2id hash ensures absent accounts perform password work.
# It has no corresponding application account or usable known credential.
_DUMMY_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$SqktBvCDDR0j35aTAWOiug$"
    "EXZ2daKVjq9lBEeWvOCav7J5UYePJDI1jB3CcV/7vJ8"
)


@dataclass(frozen=True)
class NewSession:
    session: UserSession
    token: str
    csrf_token: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password must not be empty")
    return _PASSWORD_HASH.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _PASSWORD_HASH.verify(password, password_hash)
    except (TypeError, ValueError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authenticate_credentials(db: Session, email: str, password: str) -> User | None:
    normalized = normalize_email(email)
    user = db.scalar(select(User).where(func.lower(User.email) == normalized))
    candidate_hash = user.password_hash if user and user.password_hash else _DUMMY_PASSWORD_HASH
    try:
        password_valid, updated_hash = _PASSWORD_HASH.verify_and_update(
            password, candidate_hash
        )
    except (TypeError, ValueError):
        password_valid, updated_hash = False, None
    if user is None or not user.is_active or not user.password_hash or not password_valid:
        return None

    # Transparently upgrade an authenticated hash when pwdlib's policy changes.
    if updated_hash:
        user.password_hash = updated_hash
        user.password_changed_at = utc_now()
    return user


def create_session(
    db: Session,
    user: User,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> NewSession:
    settings = settings or get_settings()
    now = now or utc_now()
    raw_token = secrets.token_urlsafe(settings.session_token_bytes)
    raw_csrf_token = secrets.token_urlsafe(settings.session_token_bytes)
    session = UserSession(
        token_hash=hash_token(raw_token),
        csrf_token_hash=hash_token(raw_csrf_token),
        user_id=user.id,
        created_at=now,
        expires_at=now + timedelta(minutes=settings.session_absolute_timeout_minutes),
        last_seen_at=now,
    )
    db.add(session)
    db.flush()
    return NewSession(session=session, token=raw_token, csrf_token=raw_csrf_token)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def load_valid_session(
    db: Session,
    raw_token: str | None,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    touch: bool = False,
) -> UserSession | None:
    settings = settings or get_settings()
    now = now or utc_now()
    if not raw_token or len(raw_token) > 512:
        return None
    session = db.scalar(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(UserSession.token_hash == hash_token(raw_token))
    )
    if session is None or session.revoked_at is not None or not session.user.is_active:
        return None
    if _as_utc(session.expires_at) <= now:
        return None
    idle_deadline = _as_utc(session.last_seen_at) + timedelta(
        minutes=settings.session_idle_timeout_minutes
    )
    if idle_deadline <= now:
        return None
    if touch:
        session.last_seen_at = min(now, _as_utc(session.expires_at))
    return session


def revoke_session(session: UserSession, *, now: datetime | None = None) -> None:
    if session.revoked_at is None:
        session.revoked_at = now or utc_now()


def verify_csrf(session: UserSession, supplied_token: str | None) -> bool:
    if not supplied_token or len(supplied_token) > 512:
        return False
    return hmac.compare_digest(hash_token(supplied_token), session.csrf_token_hash)


def rotate_csrf_token(
    session: UserSession,
    *,
    settings: Settings | None = None,
) -> str:
    """Rotate one session's CSRF secret and return the raw value once."""
    settings = settings or get_settings()
    raw_csrf_token = secrets.token_urlsafe(settings.session_token_bytes)
    session.csrf_token_hash = hash_token(raw_csrf_token)
    return raw_csrf_token
