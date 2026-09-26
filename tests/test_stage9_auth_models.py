from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import UniqueConstraint

from app.core import security
from app.core.config import Settings
from app.db.initialization import _startup_managed_tables
from app.db.models import User, UserSession
from app.schemas.user import UserRead


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg2://unused:unused@localhost/unused",
        "app_environment": "development",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_user_authentication_columns_are_nullable():
    table = User.__table__
    assert table.c.password_hash.nullable is True
    assert table.c.password_changed_at.nullable is True
    assert table.c.last_login_at.nullable is True


def test_password_hash_is_not_serialized_by_user_read():
    user = SimpleNamespace(
        id=1,
        name="Test User",
        email="test@example.com",
        created_at=datetime.now(timezone.utc),
        is_active=True,
        teams=[],
        password_hash="must-never-be-serialized",
    )
    serialized = UserRead.model_validate(user).model_dump()
    assert "password_hash" not in serialized
    assert "password_changed_at" not in serialized


def test_user_session_requires_hash_columns_and_has_no_raw_token_fields():
    table = UserSession.__table__
    assert table.c.token_hash.nullable is False
    assert table.c.csrf_token_hash.nullable is False
    assert "token" not in table.c
    assert "csrf_token" not in table.c
    assert not hasattr(UserSession, "token")
    assert not hasattr(UserSession, "csrf_token")


def test_session_token_hash_is_unique_and_indexed():
    table = UserSession.__table__
    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    index_columns = {
        tuple(column.name for column in index.columns)
        for index in table.indexes
    }
    assert ("token_hash",) in unique_columns
    assert ("token_hash",) in index_columns
    assert ("user_id",) in index_columns


def test_user_session_foreign_key_and_relationship_target_user():
    foreign_key = next(iter(UserSession.__table__.c.user_id.foreign_keys))
    assert foreign_key.target_fullname == "users.id"
    assert foreign_key.ondelete == "CASCADE"
    assert UserSession.user.property.mapper.class_ is User
    assert User.sessions.property.mapper.class_ is UserSession


def test_startup_metadata_excludes_authentication_table():
    assert "user_sessions" not in {
        table.name for table in _startup_managed_tables()
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "app_environment": "production",
            "session_cookie_name": "__Host-secure_document_session",
            "session_cookie_secure": False,
        },
        {
            "app_environment": "production",
            "session_cookie_name": "secure_document_session",
            "session_cookie_secure": True,
        },
        {
            "app_environment": "production",
            "session_cookie_name": "__Host-secure_document_session",
            "session_cookie_secure": True,
            "session_cookie_path": "/api",
        },
    ],
)
def test_auth_settings_reject_insecure_production_cookie_configuration(overrides):
    with pytest.raises(ValidationError):
        _settings(**overrides)


def test_local_cookie_configuration_remains_usable_over_http():
    settings = _settings()
    assert settings.session_cookie_name == "secure_document_session"
    assert settings.session_cookie_secure is False
    assert settings.session_cookie_path == "/"
    assert settings.session_token_bytes >= 32


def test_secure_host_cookie_configuration_is_valid_for_production():
    settings = _settings(
        app_environment="production",
        session_cookie_name="__Host-secure_document_session",
        session_cookie_secure=True,
        session_cookie_path="/",
        frontend_allowed_origins=["https://documents.example.test"],
    )
    assert settings.session_cookie_secure is True


@pytest.mark.parametrize(
    "overrides",
    [
        {"app_environment": "production", "session_cookie_name": "__Host-session", "session_cookie_secure": True, "frontend_allowed_origins": ["http://documents.example.test"]},
        {"session_absolute_timeout_minutes": 43_201},
        {"session_idle_timeout_minutes": 1_441},
    ],
)
def test_deployment_configuration_rejects_unsafe_origins_and_timeouts(overrides):
    with pytest.raises(ValidationError):
        _settings(**overrides)


def test_development_user_id_is_not_a_runtime_setting():
    settings = _settings(development_user_id=7)
    assert not hasattr(settings, "development_user_id")
