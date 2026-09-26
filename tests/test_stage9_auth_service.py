from datetime import timedelta

from app.core.config import Settings
from app.db.models import User, UserSession
from app.services.auth_service import (
    authenticate_credentials,
    create_session,
    hash_password,
    hash_token,
    load_valid_session,
    revoke_session,
    utc_now,
    verify_csrf,
    verify_password,
)


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "sqlite+pysqlite:///:memory:",
        "app_environment": "development",
        "session_absolute_timeout_minutes": 60,
        "session_idle_timeout_minutes": 15,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _user(db, *, email="user@example.com", password="correct horse", active=True):
    user = User(
        name="Test User",
        email=email,
        is_active=active,
        password_hash=hash_password(password) if password is not None else None,
    )
    db.add(user)
    db.commit()
    return user


def test_argon2id_hashing_and_verification():
    password_hash = hash_password("correct horse")
    assert password_hash != "correct horse"
    assert password_hash.startswith("$argon2id$")
    assert verify_password("correct horse", password_hash) is True
    assert verify_password("wrong", password_hash) is False
    assert "password" not in User.__table__.c


def test_authenticate_credentials_normalizes_email(isolated_auth_db):
    user = _user(isolated_auth_db, email="person@example.com")
    assert authenticate_credentials(
        isolated_auth_db, "  PERSON@example.com ", "correct horse"
    ).id == user.id


def test_all_invalid_credential_states_return_same_service_result(isolated_auth_db):
    _user(isolated_auth_db, email="valid@example.com")
    _user(isolated_auth_db, email="inactive@example.com", active=False)
    _user(isolated_auth_db, email="missing@example.com", password=None)
    assert authenticate_credentials(isolated_auth_db, "unknown@example.com", "wrong") is None
    assert authenticate_credentials(isolated_auth_db, "valid@example.com", "wrong") is None
    assert authenticate_credentials(isolated_auth_db, "inactive@example.com", "correct horse") is None
    assert authenticate_credentials(isolated_auth_db, "missing@example.com", "correct horse") is None


def test_create_session_stores_only_independent_hashes(isolated_auth_db):
    user = _user(isolated_auth_db)
    created = create_session(isolated_auth_db, user, settings=_settings())
    assert created.token != created.csrf_token
    assert created.session.token_hash == hash_token(created.token)
    assert created.session.csrf_token_hash == hash_token(created.csrf_token)
    assert created.token not in created.session.token_hash
    assert created.csrf_token not in created.session.csrf_token_hash


def test_valid_session_and_csrf_validation(isolated_auth_db):
    user = _user(isolated_auth_db)
    now = utc_now()
    created = create_session(isolated_auth_db, user, settings=_settings(), now=now)
    isolated_auth_db.commit()
    loaded = load_valid_session(
        isolated_auth_db, created.token, settings=_settings(), now=now
    )
    assert loaded.id == created.session.id
    assert verify_csrf(loaded, created.csrf_token) is True
    assert verify_csrf(loaded, "wrong") is False


def test_invalid_session_states_fail_closed(isolated_auth_db):
    user = _user(isolated_auth_db)
    settings = _settings()
    now = utc_now()

    absolute = create_session(isolated_auth_db, user, settings=settings, now=now)
    absolute.session.expires_at = now - timedelta(seconds=1)
    idle = create_session(isolated_auth_db, user, settings=settings, now=now)
    idle.session.last_seen_at = now - timedelta(minutes=16)
    revoked = create_session(isolated_auth_db, user, settings=settings, now=now)
    revoke_session(revoked.session, now=now)
    isolated_auth_db.commit()

    assert load_valid_session(isolated_auth_db, None, settings=settings, now=now) is None
    assert load_valid_session(isolated_auth_db, "x" * 513, settings=settings, now=now) is None
    assert load_valid_session(isolated_auth_db, "unknown", settings=settings, now=now) is None
    assert load_valid_session(isolated_auth_db, absolute.token, settings=settings, now=now) is None
    assert load_valid_session(isolated_auth_db, idle.token, settings=settings, now=now) is None
    assert load_valid_session(isolated_auth_db, revoked.token, settings=settings, now=now) is None


def test_inactive_user_invalidates_existing_session(isolated_auth_db):
    user = _user(isolated_auth_db)
    settings = _settings()
    created = create_session(isolated_auth_db, user, settings=settings)
    user.is_active = False
    isolated_auth_db.commit()
    assert load_valid_session(isolated_auth_db, created.token, settings=settings) is None
