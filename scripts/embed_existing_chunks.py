"""Incrementally embed existing Stage 3 chunks without resetting data."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Document
from app.services.embedding_service import embed_document


def main() -> None:
    settings = get_settings()
    with SessionLocal() as db:
        documents = db.scalars(select(Document).where((Document.embedding_version != settings.embedding_version) | (Document.embedding_status != "embedded")).order_by(Document.id)).all()
        for document in documents:
            embed_document(db, document)
            print(f"document_id={document.id} status={document.embedding_status} count={document.embedding_count}")


if __name__ == "__main__":
    main()
