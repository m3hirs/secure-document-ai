"""Tests for the document summarization API."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.security import Principal, get_current_principal
from app.db.database import get_db
from app.main import app
from app.services.llm_service import LocalLLMError


def test_ollama_failure_returns_503():
    def fake_db():
        yield object()

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[get_current_principal] = (
        lambda: Principal(user_id=1)
    )

    try:
        with patch(
            "app.api.summaries.summarize_document",
            side_effect=LocalLLMError("Connection refused"),
        ):
            with TestClient(app) as client:
                response = client.post("/documents/31/summarize")

        assert response.status_code == 503
        assert response.json() == {
            "detail": "Local summarization service is unavailable"
        }

        # Internal connection details must not be exposed to the client.
        assert "Connection refused" not in response.text

    finally:
        app.dependency_overrides.clear()