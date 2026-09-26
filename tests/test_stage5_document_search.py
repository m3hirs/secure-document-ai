from sqlalchemy import select

from app.db.models import Document
from app.services.semantic_search_service import document_accessible_clause


def test_document_access_requires_shared_team():
    statement = select(Document).where(
        document_accessible_clause(user_id=1)
    )

    sql = str(statement.compile())

    assert "EXISTS" in sql.upper()
    assert "document_teams" in sql
    assert "user_teams" in sql
    assert "team_id" in sql
    assert "user_id" in sql


def test_document_access_is_bound_to_requested_user():
    statement = select(Document).where(
        document_accessible_clause(user_id=123)
    )

    compiled = statement.compile()

    assert 123 in compiled.params.values()