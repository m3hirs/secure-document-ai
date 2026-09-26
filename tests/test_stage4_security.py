from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core import security


def test_missing_session_identity_fails_closed(monkeypatch):
    monkeypatch.setattr(
        security,
        "get_settings",
        lambda: SimpleNamespace(session_cookie_name="secure_document_session"),
    )
    with pytest.raises(HTTPException) as error:
        security.get_current_principal(
            SimpleNamespace(cookies={}),
            SimpleNamespace(),
        )
    assert error.value.status_code == 401


def test_current_identity_comes_from_validated_session(monkeypatch):
    settings = SimpleNamespace(session_cookie_name="secure_document_session")
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setattr(
        security,
        "load_valid_session",
        lambda db, token, settings: SimpleNamespace(id=12, user_id=7),
    )
    principal = security.get_current_principal(
        SimpleNamespace(cookies={"secure_document_session": "opaque"}),
        SimpleNamespace(),
    )
    assert principal.user_id == 7
    assert principal.session_id == 12
