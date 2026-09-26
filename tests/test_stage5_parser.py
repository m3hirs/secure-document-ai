from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from app.services.natural_search_parser import parse_query

class Scalar:
    def __init__(self, values): self.values=values
    def all(self): return self.values
class DB:
    def scalars(self, statement): return Scalar([])

def test_empty_query_is_rejected():
    with pytest.raises(HTTPException): parse_query(DB(), " ", 1, "Asia/Kolkata")

def test_month_without_year_is_rejected():
    with pytest.raises(HTTPException): parse_query(DB(), "uploaded in September", 1, "Asia/Kolkata")

def test_relative_dates_are_deterministic():
    parsed=parse_query(DB(), "PDFs uploaded in the last 10 days", 1, "Asia/Kolkata", datetime(2026,9,20,tzinfo=ZoneInfo("Asia/Kolkata")))
    assert parsed.file_type == "application/pdf"
    assert parsed.start is not None and parsed.end is not None
def test_from_my_team_is_explicitly_rejected():
    from unittest.mock import Mock
    from fastapi import HTTPException

    from app.services.natural_search_parser import parse_query

    db = Mock()

    with pytest.raises(HTTPException) as exc:
        parse_query(
            db=db,
            query="Show confidential documents from my team",
            user_id=1,
            timezone_name="Asia/Kolkata",
        )

    assert exc.value.status_code == 422
    assert "team filtering is not yet supported" in exc.value.detail