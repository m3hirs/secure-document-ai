from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import get_settings


CHUNK_SIZE = 1024 * 1024


def storage_directory() -> Path:
    directory = get_settings().document_storage_dir
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_pdf(upload: UploadFile) -> tuple[str, int]:
    """Stream a validated PDF to an internal UUID-based filename."""
    first_bytes = upload.file.read(5)
    if first_bytes != b"%PDF-":
        raise ValueError("Uploaded file is not a valid PDF")
    stored_name = f"{uuid4().hex}.pdf"
    destination = storage_directory() / stored_name
    size = 0
    try:
        with destination.open("wb") as target:
            target.write(first_bytes)
            size += len(first_bytes)
            while chunk := upload.file.read(CHUNK_SIZE):
                target.write(chunk)
                size += len(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    finally:
        upload.file.seek(0)
    return stored_name, size


def delete_stored_file(stored_name: str) -> None:
    (storage_directory() / stored_name).unlink(missing_ok=True)
