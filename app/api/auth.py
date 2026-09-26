from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    SessionPrincipal,
    get_current_principal,
    require_allowed_origin,
    require_csrf_protection,
)
from app.db.database import get_db
from app.db.models import User, UserSession
from app.schemas.auth import (
    AuthUserRead,
    CsrfRotationRequest,
    CsrfTokenResponse,
    LoginRequest,
    LoginResponse,
    LogoutResponse,
)
from app.services.auth_service import (
    authenticate_credentials,
    create_session,
    revoke_session,
    rotate_csrf_token,
    utc_now,
)


router = APIRouter(prefix="/auth", tags=["auth"])
_INVALID_CREDENTIALS = "Invalid email or password"


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_absolute_timeout_minutes * 60,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,
        path=settings.session_cookie_path,
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    settings = get_settings()
    require_allowed_origin(request, settings)
    user = authenticate_credentials(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_INVALID_CREDENTIALS)

    new_session = create_session(db, user, settings=settings)
    user.last_login_at = utc_now()
    db.commit()
    _set_session_cookie(response, new_session.token, settings)
    return LoginResponse(
        user=AuthUserRead.model_validate(user),
        csrf_token=new_session.csrf_token,
    )


@router.get("/me", response_model=AuthUserRead)
def me(
    principal: SessionPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> AuthUserRead:
    user = db.scalar(select(User).where(User.id == principal.user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Authentication required")
    return AuthUserRead.model_validate(user)


@router.post("/csrf", response_model=CsrfTokenResponse)
def rotate_csrf(
    request: Request,
    payload: CsrfRotationRequest = Body(default_factory=CsrfRotationRequest),
    principal: SessionPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> CsrfTokenResponse:
    """Issue a fresh CSRF token for the authenticated browser session."""
    settings = get_settings()
    require_allowed_origin(request, settings)
    session = db.scalar(
        select(UserSession).where(UserSession.id == principal.session_id)
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    csrf_token = rotate_csrf_token(session, settings=settings)
    db.commit()
    return CsrfTokenResponse(csrf_token=csrf_token)


@router.post("/logout", response_model=LogoutResponse)
def logout(
    request: Request,
    response: Response,
    principal: SessionPrincipal = Depends(get_current_principal),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db),
) -> LogoutResponse:
    settings = get_settings()
    session = db.scalar(
        select(UserSession).where(UserSession.id == principal.session_id)
    )
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    revoke_session(session)
    db.commit()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
    return LogoutResponse(message="Logged out")
