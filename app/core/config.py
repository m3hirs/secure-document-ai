from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
class Settings(BaseSettings):
    database_url: str
    document_storage_dir: Path = PROJECT_ROOT / "data" / "documents"
    chunk_max_characters: int = 1500
    chunk_overlap_characters: int = 200
    chunking_version: str = "v1"
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    embedding_model_cache_dir: Path = Path(r"E:\AI-Models")
    embedding_dimension: int = 384
    embedding_batch_size: int = 16
    embedding_version: str = "e5-small-v1"
    semantic_search_top_k: int = 10
    semantic_search_max_top_k: int = 50
    semantic_search_min_similarity: float = 0.81
    app_environment: str = "development"
    app_timezone: str = "Asia/Kolkata"
    session_cookie_name: str = "secure_document_session"
    session_absolute_timeout_minutes: int = 480
    session_idle_timeout_minutes: int = 30
    session_cookie_secure: bool = False
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    session_cookie_path: str = "/"
    session_token_bytes: int = 32
    frontend_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    @model_validator(mode="after")
    def validate_chunking(self):
        if self.chunk_max_characters <= 0:
            raise ValueError("CHUNK_MAX_CHARACTERS must be greater than zero")
        if self.chunk_overlap_characters < 0 or self.chunk_overlap_characters >= self.chunk_max_characters:
            raise ValueError("CHUNK_OVERLAP_CHARACTERS must be non-negative and smaller than CHUNK_MAX_CHARACTERS")
        if self.embedding_dimension != 384 or self.embedding_batch_size <= 0:
            raise ValueError("EMBEDDING_DIMENSION must be 384 and EMBEDDING_BATCH_SIZE must be positive")
        if self.semantic_search_top_k <= 0 or self.semantic_search_max_top_k <= 0 or self.semantic_search_top_k > self.semantic_search_max_top_k:
            raise ValueError("semantic search limits must be positive and default top_k cannot exceed max_top_k")
        if not 0.0 <= self.semantic_search_min_similarity <= 1.0:
            raise ValueError("SEMANTIC_SEARCH_MIN_SIMILARITY must be between 0 and 1")
        return self

    @model_validator(mode="after")
    def validate_authentication_foundation(self):
        if self.session_absolute_timeout_minutes <= 0:
            raise ValueError("SESSION_ABSOLUTE_TIMEOUT_MINUTES must be positive")
        if self.session_absolute_timeout_minutes > 43_200:
            raise ValueError("SESSION_ABSOLUTE_TIMEOUT_MINUTES cannot exceed 30 days")
        if self.session_idle_timeout_minutes <= 0:
            raise ValueError("SESSION_IDLE_TIMEOUT_MINUTES must be positive")
        if self.session_idle_timeout_minutes > 1_440:
            raise ValueError("SESSION_IDLE_TIMEOUT_MINUTES cannot exceed 24 hours")
        if self.session_idle_timeout_minutes > self.session_absolute_timeout_minutes:
            raise ValueError(
                "SESSION_IDLE_TIMEOUT_MINUTES cannot exceed the absolute timeout"
            )
        if self.session_token_bytes < 32:
            raise ValueError("SESSION_TOKEN_BYTES must be at least 32")
        if not self.session_cookie_name.strip():
            raise ValueError("SESSION_COOKIE_NAME must not be empty")
        if not self.session_cookie_path.startswith("/"):
            raise ValueError("SESSION_COOKIE_PATH must be an absolute cookie path")

        is_host_cookie = self.session_cookie_name.startswith("__Host-")
        if is_host_cookie and (
            not self.session_cookie_secure or self.session_cookie_path != "/"
        ):
            raise ValueError(
                "__Host- cookies require Secure=true and Path=/"
            )
        if self.session_cookie_samesite == "none" and not self.session_cookie_secure:
            raise ValueError("SameSite=None cookies require Secure=true")

        normalized_origins: list[str] = []
        for origin in self.frontend_allowed_origins:
            normalized = origin.strip().rstrip("/")
            parsed = urlsplit(normalized)
            if (
                not normalized
                or normalized == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "FRONTEND_ALLOWED_ORIGINS must contain exact HTTP(S) origins"
                )
            normalized_origins.append(normalized)
        if not normalized_origins:
            raise ValueError("FRONTEND_ALLOWED_ORIGINS must not be empty")
        self.frontend_allowed_origins = normalized_origins

        if self.app_environment.lower() == "production":
            if not self.session_cookie_secure:
                raise ValueError("Production session cookies must be Secure")
            if not is_host_cookie:
                raise ValueError(
                    "Production session cookies must use the __Host- prefix"
                )
            if self.session_cookie_path != "/":
                raise ValueError("Production session cookie Path must be /")
            if any(urlsplit(origin).scheme != "https" for origin in normalized_origins):
                raise ValueError("Production frontend origins must use HTTPS")
        return self

@lru_cache
def get_settings() -> Settings: return Settings()
