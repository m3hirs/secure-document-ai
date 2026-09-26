from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy import select

from app.api import auth as auth_api
from app.core import security
from app.core.config import Settings
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.database import get_db
from app.db.models import Classification, User, UserSession
from app.main import app
from app.services import auth_service
from app.services.auth_service import create_session, hash_password, hash_token


ORIGIN = "http://localhost:5173"
PASSWORD = "correct horse battery staple"


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "app_environment": "development",
        "frontend_allowed_origins": [ORIGIN],
        "session_absolute_timeout_minutes": 60,
        "session_idle_timeout_minutes": 15,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def auth_client(isolated_auth_db, monkeypatch):
    settings = _settings()
    user = User(
        name="Test User",
        email="user@example.com",
        is_active=True,
        password_hash=hash_password(PASSWORD),
    )
    isolated_auth_db.add(user)
    isolated_auth_db.commit()

    def override_db():
        yield isolated_auth_db

    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_service, "get_settings", lambda: settings)
    client = TestClient(app)
    try:
        yield client, isolated_auth_db, user, settings
    finally:
        client.close()
        app.dependency_overrides.clear()


def _login(client, **extra):
    payload = {"email": "user@example.com", "password": PASSWORD}
    payload.update(extra)
    return client.post("/auth/login", json=payload, headers={"Origin": ORIGIN})


def test_valid_login_creates_hashed_session_and_safe_response(auth_client):
    client, db, user, settings = auth_client
    response = _login(client)
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_active": True,
    }
    assert set(body) == {"user", "csrf_token"}
    assert "password_hash" not in response.text
    assert "token_hash" not in response.text
    assert "session" not in body
    session = db.scalar(select(UserSession))
    assert session is not None
    assert session.csrf_token_hash == hash_token(body["csrf_token"])
    assert session.token_hash != client.cookies.get(settings.session_cookie_name)
    assert user.last_login_at is not None


@pytest.mark.parametrize(
    ("email", "password", "user_change"),
    [
        ("unknown@example.com", "wrong", None),
        ("user@example.com", "wrong", None),
        ("user@example.com", PASSWORD, "inactive"),
        ("user@example.com", PASSWORD, "missing_hash"),
    ],
)
def test_invalid_login_states_have_identical_response(auth_client, email, password, user_change):
    client, db, user, _ = auth_client
    if user_change == "inactive":
        user.is_active = False
        db.commit()
    elif user_change == "missing_hash":
        user.password_hash = None
        db.commit()
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}


def test_login_cookie_security_attributes(auth_client):
    client, _, _, settings = auth_client
    response = _login(client)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=lax" in cookie
    assert "path=/" in cookie
    assert f"max-age={settings.session_absolute_timeout_minutes * 60}" in cookie


def test_production_cookie_has_secure_and_host_constraints(auth_client, monkeypatch):
    client, _, _, _ = auth_client
    production = _settings(
        app_environment="production",
        session_cookie_name="__Host-secure_document_session",
        session_cookie_secure=True,
        frontend_allowed_origins=["https://documents.example.test"],
    )
    monkeypatch.setattr(auth_api, "get_settings", lambda: production)
    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": PASSWORD},
        headers={"Origin": "https://documents.example.test"},
    )
    cookie = response.headers["set-cookie"]
    assert "__Host-secure_document_session=" in cookie
    assert "Secure" in cookie
    assert "Path=/" in cookie
    assert "Domain=" not in cookie


def test_authenticated_classifications_are_safe_and_sorted(auth_client):
    client, db, _, _ = auth_client
    Classification.__table__.create(bind=db.get_bind(), checkfirst=True)
    db.add_all([
        Classification(name="Restricted", description="not returned"),
        Classification(name="Internal", description="not returned"),
    ])
    db.commit()
    login = _login(client)
    assert login.status_code == 200
    response = client.get("/classifications")
    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == ["Internal", "Restricted"]
    assert all(set(item) == {"id", "name"} for item in body)
    assert "description" not in response.text


def test_classifications_require_authentication(auth_client):
    client, db, _, _ = auth_client
    Classification.__table__.create(bind=db.get_bind(), checkfirst=True)
    response = client.get("/classifications")
    assert response.status_code == 401


def test_security_headers_are_present_without_development_csp(auth_client):
    client, _, _, _ = auth_client
    response = client.get("/auth/me")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert "camera=()" in response.headers["permissions-policy"]
    assert "content-security-policy" not in response.headers


def test_production_security_headers_include_restrictive_csp():
    test_app = FastAPI()
    test_app.add_middleware(SecurityHeadersMiddleware, production=True)

    @test_app.get("/")
    def root():
        return {"ok": True}

    with TestClient(test_app) as client:
        response = client.get("/")
    policy = response.headers["content-security-policy"]
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "unsafe-inline" not in policy
    assert "unsafe-eval" not in policy
    assert "strict-transport-security" not in response.headers


def test_origin_is_checked_before_login_and_logout(auth_client):
    client, _, _, _ = auth_client
    bad_login = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert bad_login.status_code == 403

    login = _login(client)
    bad_logout = client.post(
        "/auth/logout",
        headers={
            "Origin": "https://evil.example",
            "X-CSRF-Token": login.json()["csrf_token"],
        },
    )
    assert bad_logout.status_code == 403


def test_me_requires_cookie_and_returns_safe_user(auth_client):
    client, _, user, settings = auth_client
    assert client.get("/auth/me").status_code == 401
    login = _login(client)
    assert login.status_code == 200
    response = client.get("/auth/me?user_id=999")
    assert response.status_code == 200
    assert response.json()["id"] == user.id
    assert "password" not in response.text
    assert "hash" not in response.text
    client.cookies.set(settings.session_cookie_name, "unknown")
    assert client.get("/auth/me").status_code == 401


def test_malformed_revoked_and_inactive_sessions_are_unauthorized(auth_client):
    client, db, user, settings = auth_client
    client.cookies.set(settings.session_cookie_name, "x" * 513)
    assert client.get("/auth/me").status_code == 401

    created = create_session(db, user, settings=settings)
    db.commit()
    client.cookies.set(settings.session_cookie_name, created.token)
    created.session.revoked_at = auth_service.utc_now()
    db.commit()
    assert client.get("/auth/me").status_code == 401

    created.session.revoked_at = None
    user.is_active = False
    db.commit()
    assert client.get("/auth/me").status_code == 401


def test_logout_csrf_and_revocation(auth_client):
    client, db, _, settings = auth_client
    login = _login(client)
    csrf = login.json()["csrf_token"]
    assert client.post("/auth/logout", headers={"Origin": ORIGIN}).status_code == 403
    assert client.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong"},
    ).status_code == 403

    other_user = User(
        name="Other", email="other@example.com", is_active=True, password_hash=hash_password(PASSWORD)
    )
    db.add(other_user)
    db.commit()
    other = create_session(db, other_user, settings=settings)
    db.commit()
    assert client.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "X-CSRF-Token": other.csrf_token},
    ).status_code == 403

    response = client.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Logged out"}
    session = db.scalar(select(UserSession).where(UserSession.user_id != other_user.id))
    assert session.revoked_at is not None
    cookie = response.headers["set-cookie"].lower()
    assert "max-age=0" in cookie
    assert "token_hash" not in response.text
    assert client.get("/auth/me").status_code == 401
    repeated = client.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert repeated.status_code == 401
    assert repeated.json() == {"detail": "Authentication required"}


def test_csrf_rotation_replaces_hash_and_new_token_protects_logout(auth_client, caplog):
    client, db, _, _ = auth_client
    login = _login(client)
    previous_token = login.json()["csrf_token"]
    session = db.scalar(select(UserSession))
    previous_hash = session.csrf_token_hash

    response = client.post("/auth/csrf", json={}, headers={"Origin": ORIGIN})

    assert response.status_code == 200
    assert set(response.json()) == {"csrf_token"}
    new_token = response.json()["csrf_token"]
    assert new_token != previous_token
    db.refresh(session)
    assert session.csrf_token_hash == hash_token(new_token)
    assert session.csrf_token_hash != previous_hash
    assert new_token not in response.headers.get("set-cookie", "")
    assert "csrf_token_hash" not in response.text
    assert "token_hash" not in response.text
    assert all(
        new_token not in record.getMessage()
        and previous_token not in record.getMessage()
        for record in caplog.records
    )

    old_token_logout = client.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "X-CSRF-Token": previous_token},
    )
    assert old_token_logout.status_code == 403
    new_token_logout = client.post(
        "/auth/logout",
        headers={"Origin": ORIGIN, "X-CSRF-Token": new_token},
    )
    assert new_token_logout.status_code == 200


def test_csrf_rotation_requires_cookie_and_exact_origin(auth_client):
    client, _, _, settings = auth_client
    assert client.post("/auth/csrf", json={}, headers={"Origin": ORIGIN}).status_code == 401

    assert _login(client).status_code == 200
    assert client.post("/auth/csrf", json={}).status_code == 403
    assert client.post(
        "/auth/csrf",
        json={},
        headers={"Origin": "https://evil.example"},
    ).status_code == 403

    client.cookies.set(settings.session_cookie_name, "invalid-session-token")
    assert client.post(
        "/auth/csrf", json={}, headers={"Origin": ORIGIN}
    ).status_code == 401


@pytest.mark.parametrize("invalid_state", ["revoked", "expired", "inactive"])
def test_csrf_rotation_rejects_invalid_session_states(auth_client, invalid_state):
    client, db, user, _ = auth_client
    assert _login(client).status_code == 200
    session = db.scalar(select(UserSession))
    if invalid_state == "revoked":
        session.revoked_at = auth_service.utc_now()
    elif invalid_state == "expired":
        session.expires_at = auth_service.utc_now() - timedelta(seconds=1)
    else:
        user.is_active = False
    db.commit()

    response = client.post("/auth/csrf", json={}, headers={"Origin": ORIGIN})
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_csrf_rotation_rejects_client_supplied_identity(auth_client):
    client, _, _, _ = auth_client
    assert _login(client).status_code == 200
    response = client.post(
        "/auth/csrf",
        json={"user_id": 999},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 422


def test_login_rejects_client_supplied_identity(auth_client):
    client, _, _, _ = auth_client
    response = _login(client, user_id=999)
    assert response.status_code == 422


def test_no_cookie_cannot_activate_a_development_identity(auth_client):
    client, _, _, settings = auth_client
    client.cookies.delete(settings.session_cookie_name)
    assert client.get("/auth/me?user_id=17").status_code == 401
