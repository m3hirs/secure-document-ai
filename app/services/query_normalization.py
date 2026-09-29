"""Conservative normalization shared by query and document resolution."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata


_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
}

_DOCUMENT_WORDS = {
    "documents": "document",
    "pdfs": "pdf",
    "resumes": "resume",
}

_QUERY_STOP_WORDS = {
    "about",
    "accessible",
    "all",
    "are",
    "contain",
    "contains",
    "document",
    "documents",
    "explain",
    "find",
    "for",
    "from",
    "give",
    "have",
    "in",
    "information",
    "is",
    "listed",
    "me",
    "mentioned",
    "my",
    "of",
    "pdf",
    "pdfs",
    "resume",
    "resumes",
    "show",
    "summary",
    "summarise",
    "summarize",
    "tell",
    "the",
    "this",
    "what",
    "which",
    "with",
}


def normalize_literal_text(value: str) -> str:
    """Normalize Unicode, case, and repeated whitespace for literal evidence."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_search_text(
    value: str,
    *,
    strip_pdf_extension: bool = False,
    singularize_document_words: bool = False,
) -> str:
    """Normalize safe filename/query variants without collapsing token order.

    Punctuation and common filename separators become spaces. Number words from
    zero through ten become digits. No stemming or phonetic expansion is used.
    """
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    if strip_pdf_extension:
        normalized = re.sub(r"\.pdf\s*$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"(?:['’]s)\b", "", normalized)
    normalized = re.sub(r"[_\-./\\]+", " ", normalized)
    tokens = []
    for token in re.findall(r"[^\W_]+", normalized, re.UNICODE):
        token = _NUMBER_WORDS.get(token, token)
        if token.isdigit():
            token = str(int(token))
        tokens.append(token)
    normalized = " ".join(tokens)
    if singularize_document_words:
        normalized = " ".join(
            _DOCUMENT_WORDS.get(token, token) for token in normalized.split()
        )
    return re.sub(r"\s+", " ", normalized).strip()


def normalize_document_name(value: str, *, strip_extension: bool = True) -> str:
    """Return a comparison key for a user-supplied or stored document name."""
    return normalize_search_text(
        value,
        strip_pdf_extension=strip_extension,
        singularize_document_words=True,
    )


def document_name_aliases(value: str) -> tuple[str, ...]:
    """Return conservative ordered aliases for one filename or target."""
    normalized = normalize_document_name(value)
    aliases = [normalized]
    tokens = normalized.split()
    if tokens and tokens[0] == "the":
        aliases.append(" ".join(tokens[1:]))
    if tokens and tokens[-1] in {"document", "pdf", "resume"}:
        aliases.append(" ".join(tokens[:-1]))
    return tuple(dict.fromkeys(alias for alias in aliases if alias))


def lexical_query_tokens(value: str) -> tuple[str, ...]:
    """Return stable substantive query terms for lexical retrieval."""
    normalized = normalize_search_text(
        value,
        singularize_document_words=True,
    )
    return tuple(dict.fromkeys(
        token
        for token in normalized.split()
        if (len(token) >= 3 or token.isdigit()) and token not in _QUERY_STOP_WORDS
    ))


def normalized_filename_stem(filename: str) -> str:
    """Normalize a stored filename basename for lexical scoring."""
    return normalize_document_name(Path(filename).name, strip_extension=True)
