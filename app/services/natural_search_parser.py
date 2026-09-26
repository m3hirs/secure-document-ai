"""Small deterministic parser for explicitly supported metadata phrases."""
from __future__ import annotations
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.db.models import Classification, Tag, Team, User

@dataclass(frozen=True)
class ParsedSearch:
    topic: str | None; file_type: str | None; uploader_id: int | None; team_id: int | None; classification_id: int | None; tag_id: int | None; start: datetime | None; end: datetime | None; mode: str

def _one(db: Session, model, name: str, label: str):
    rows=db.scalars(select(model).where(func.lower(model.name)==name.strip().lower())).all()
    if len(rows)!=1: raise HTTPException(422, f"Unknown or ambiguous {label}")
    return rows[0].id

def parse_query(db: Session, query: str, user_id: int, timezone_name: str, now: datetime | None=None) -> ParsedSearch:
    text=" ".join(query.split())
    if not text: raise HTTPException(422,"Query must not be empty")
    low=text.lower(); now=now or datetime.now(ZoneInfo(timezone_name)); start=end=None; file_type=None; uploader_id=None; team_id=None; classification_id=None; tag_id=None
    if re.search(r"\bpdfs?\b|पीडीएफ",low): file_type="application/pdf"; text=re.sub(r"\bpdfs?\b|पीडीएफ", "", text, flags=re.I)
    if re.search(r"\b(i uploaded|my documents)\b|मेरे दस्तावेज",low): uploader_id=user_id; text=re.sub(r"\b(i uploaded|my documents)\b|मेरे दस्तावेज", "", text, flags=re.I)
    days=re.search(r"(?:last|पिछले)\s+(\d+)\s+(?:days?|दिन)",low)
    if days:
        end=now.astimezone(ZoneInfo(timezone_name)); start=end-timedelta(days=int(days.group(1))); text=re.sub(days.group(0),"",text,flags=re.I)
    elif "recently uploaded" in low:
        end=now; start=end-timedelta(days=7); text=re.sub("recently uploaded","",text,flags=re.I)
    between=re.search(r"uploaded between\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})\s+and\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})",text,re.I)
    if between:
        try:
            start=datetime.strptime(between.group(1).replace(",",""),"%B %d %Y").replace(tzinfo=ZoneInfo(timezone_name))
            end=datetime.strptime(between.group(2).replace(",",""),"%B %d %Y").replace(tzinfo=ZoneInfo(timezone_name))+timedelta(days=1)
        except ValueError: raise HTTPException(422,"Invalid date range")
        if start>=end: raise HTTPException(422,"Invalid date range")
        text=text.replace(between.group(0),"")
    by=re.search(r"uploaded by\s+(.+?)(?=\s+(?:from|tagged|uploaded)\b|$)",text,re.I)
    if by: uploader_id=_one(db,User,by.group(1),"uploader"); text=text.replace(by.group(0),"")
    if re.search(r"\bfrom\s+my\s+team\b", text, re.I):
        raise HTTPException(
            status_code=422,
            detail="Current-user team filtering is not yet supported",
        )
    team=re.search(r"from(?: the)?\s+(.+?)\s+team",text,re.I)
    if team:
        name=team.group(1).strip(); name="Machine Learning" if name.lower()=="ml" else name; team_id=_one(db,Team,name,"team"); text=text.replace(team.group(0),"")
    tagged=re.search(r"tagged with\s+(.+?)(?=$|\s+uploaded)",text,re.I)
    if tagged: tag_id=_one(db,Tag,tagged.group(1),"tag"); text=text.replace(tagged.group(0),"")
    for name in db.scalars(select(Classification.name)).all():
        if re.search(rf"\b{re.escape(name)}\b|{'गोपनीय' if name.lower()=='confidential' else '$^'}",text,re.I): classification_id=_one(db,Classification,name,"classification"); text=re.sub(rf"\b{re.escape(name)}\b|गोपनीय","",text,flags=re.I)
    month = re.search(
    r"\buploaded\s+in\s+(January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+(\d{4}))?\b",
    text,
    re.I,
    )
    if month:
        if not month.group(2): raise HTTPException(422,"Month filters require an explicit year")
        try: first=datetime.strptime(f"{month.group(1)} {month.group(2)}","%B %Y").replace(tzinfo=ZoneInfo(timezone_name)); start=first; end=(first.replace(day=28)+timedelta(days=4)).replace(day=1)
        except ValueError: raise HTTPException(422,"Invalid month filter")
        text=text.replace(month.group(0),"")
    topic=re.sub(r"\b(show|find|documents?|all|from my team|uploaded|in|the)\b","",text,flags=re.I).strip(" ,.") or None
    metadata=any(x is not None for x in (file_type,uploader_id,team_id,classification_id,tag_id,start,end))
    return ParsedSearch(topic,file_type,uploader_id,team_id,classification_id,tag_id,start,end,"hybrid" if metadata and topic else "metadata" if metadata else "semantic")
