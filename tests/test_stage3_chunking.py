from app.services.chunking_service import chunk_text, normalize_text


def test_normalization_preserves_paragraphs_and_normalizes_crlf():
    value = "  First\t paragraph.  \r\n\r\n\r\nSecond    paragraph.  "
    assert normalize_text(value) == "First paragraph.\n\nSecond paragraph."


def test_empty_text_creates_no_chunks():
    assert chunk_text(" \r\n\t ", maximum=20, overlap=2) == []


def test_short_text_creates_one_chunk_with_offsets():
    chunks = chunk_text("A short paragraph.", maximum=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].text == "A short paragraph."
    assert (chunks[0].start, chunks[0].end) == (0, 18)


def test_chunking_enforces_maximum_and_overlap_deterministically():
    text = "Sentence one. Sentence two. Sentence three. Sentence four."
    first = chunk_text(text, maximum=25, overlap=6)
    second = chunk_text(text, maximum=25, overlap=6)
    assert first == second
    assert len(first) > 1
    assert all(len(chunk.text) <= 25 for chunk in first)
    assert first[1].start < first[0].end


def test_chunks_are_page_local():
    first_page = chunk_text("page one " * 10, maximum=20, overlap=4)
    second_page = chunk_text("page two " * 10, maximum=20, overlap=4)
    assert all("page one" in chunk.text for chunk in first_page)
    assert all("page two" in chunk.text for chunk in second_page)
