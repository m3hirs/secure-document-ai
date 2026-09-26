from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api import auth, documents, rag, search, summaries, users
from app.core.config import get_settings
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.database import SessionLocal
from app.db.initialization import initialize_database
app=FastAPI(title="Secure Document AI",version="0.1.0")
settings=get_settings()
app.add_middleware(
 CORSMiddleware,
 allow_origins=settings.frontend_allowed_origins,
 allow_credentials=True,
 allow_methods=["GET","POST","HEAD","OPTIONS"],
 allow_headers=["Content-Type","X-CSRF-Token"],
)
app.add_middleware(
 SecurityHeadersMiddleware,
 production=settings.app_environment.lower()=="production",
)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(rag.router)
app.include_router(documents.router)
app.include_router(search.router)
app.include_router(summaries.router)
@app.on_event("startup")
def initialize_schema(): initialize_database()
@app.get("/health",tags=["system"])
def health():
 try:
  with SessionLocal() as db: db.execute(text("SELECT 1"))
  return {"status":"ok","database":"connected"}
 except Exception: return {"status":"degraded","database":"unavailable"}
