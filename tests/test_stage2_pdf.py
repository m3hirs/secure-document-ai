from io import BytesIO

import fitz
import pytest
from fastapi import UploadFile

from app.services import storage_service


def test_save_pdf_rejects_non_pdf(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_service, "storage_directory", lambda: tmp_path)
    upload = UploadFile(filename="not-a-pdf.txt", file=BytesIO(b"plain text"))
    with pytest.raises(ValueError, match="valid PDF"):
        storage_service.save_pdf(upload)


def test_save_pdf_streams_pdf_to_uuid_name(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_service, "storage_directory", lambda: tmp_path)
    pdf = fitz.open()
    pdf.new_page().insert_text((72, 72), "Stage 2 PDF test")
    data = pdf.tobytes()
    upload = UploadFile(filename="../../restricted.pdf", file=BytesIO(data))
    stored_name, size = storage_service.save_pdf(upload)
    assert stored_name.endswith(".pdf")
    assert "/" not in stored_name and "\\" not in stored_name
    assert size == len(data)
    assert (tmp_path / stored_name).read_bytes() == data
