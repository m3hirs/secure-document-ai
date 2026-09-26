from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import os

import fitz
from PIL import Image
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentEvent, DocumentPage


# ---------------------------------------------------------
# Tesseract configuration
# ---------------------------------------------------------

TESSERACT_PATH = os.getenv(
    "TESSERACT_CMD",
    r"D:\Tesseract\tesseract.exe",
)


def _configure_tesseract():
    """Configure the local Tesseract executable for pytesseract."""

    try:
        import pytesseract

        if os.path.isfile(TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
            return pytesseract

        return None

    except ImportError:
        return None


# ---------------------------------------------------------
# OCR
# ---------------------------------------------------------

def _ocr_text(page: fitz.Page) -> str | None:
    try:
        pytesseract = _configure_tesseract()

        if pytesseract is None:
            return None

        image_bytes = page.get_pixmap(
            matrix=fitz.Matrix(2, 2)
        ).tobytes("png")

        image = Image.open(BytesIO(image_bytes))

        pytesseract.get_tesseract_version()

        text = pytesseract.image_to_string(image)

        return text.strip() or None

    except (ImportError, OSError, RuntimeError):
        return None


# ---------------------------------------------------------
# PDF processing
# ---------------------------------------------------------

def process_pdf(
    db: Session,
    document: Document,
    absolute_path: Path,
) -> Document:
    """Extract page-aware PDF content, without logging or returning raw content."""

    document.processing_status = "processing"
    document.processing_started_at = datetime.now(timezone.utc)
    document.processing_error = None

    db.add(
        DocumentEvent(
            document=document,
            user_id=document.uploaded_by,
            event_type="processing_started",
            event_metadata=None,
        )
    )

    db.commit()

    try:
        db.execute(
            delete(DocumentPage).where(
                DocumentPage.document_id == document.id
            )
        )

        total_text = 0
        text_pages = 0
        images = 0
        ocr_pages = 0

        with fitz.open(absolute_path) as pdf:

            document.page_count = pdf.page_count

            for index, page in enumerate(pdf, start=1):

                # -----------------------------------------
                # Normal PDF text extraction
                # -----------------------------------------

                page_text = page.get_text("text").strip()

                # -----------------------------------------
                # Count embedded images
                # -----------------------------------------

                page_images = len(
                    page.get_images(full=True)
                )

                ocr_used = False

                # -----------------------------------------
                # OCR fallback for image-only pages
                # -----------------------------------------

                if not page_text:

                    ocr = _ocr_text(page)

                    if ocr:
                        page_text = ocr
                        ocr_used = True

                # -----------------------------------------
                # Statistics
                # -----------------------------------------

                has_text = bool(page_text)

                total_text += len(page_text)

                text_pages += int(has_text)

                images += page_images

                ocr_pages += int(ocr_used)

                # -----------------------------------------
                # Store page
                # -----------------------------------------

                db.add(
                    DocumentPage(
                        document_id=document.id,
                        page_number=index,
                        extracted_text=page_text or None,
                        has_text=has_text,
                        image_count=page_images,
                        ocr_used=ocr_used,
                    )
                )

        # ---------------------------------------------
        # Document statistics
        # ---------------------------------------------

        document.extracted_text_length = total_text

        document.text_page_count = text_pages

        document.image_count = images

        document.ocr_page_count = ocr_pages

        document.processing_status = "processed"

        document.processed_at = datetime.now(timezone.utc)

        db.add(
            DocumentEvent(
                document=document,
                user_id=document.uploaded_by,
                event_type="processing_completed",
                event_metadata={
                    "pages": document.page_count,
                    "images": images,
                    "ocr_pages": ocr_pages,
                },
            )
        )

    except Exception:

        document.processing_status = "failed"

        document.processed_at = datetime.now(timezone.utc)

        document.processing_error = "PDF processing failed"

        db.add(
            DocumentEvent(
                document=document,
                user_id=document.uploaded_by,
                event_type="processing_failed",
                event_metadata=None,
            )
        )

    db.commit()

    db.refresh(document)

    if document.processing_status == "processed":
        from app.services.chunking_service import rechunk_document
        return rechunk_document(db, document)

    return document
