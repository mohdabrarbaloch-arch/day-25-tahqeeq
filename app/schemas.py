"""Request and response schemas.

Pydantic v2 does the input validation, so the routers can assume their inputs
are already sane. Every bound here is a real limit, not decoration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings

# ── auth ─────────────────────────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=8, max_length=128)]

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if value.strip() != value:
            raise ValueError("Password must not start or end with whitespace.")
        if value.lower() in {"password", "12345678", "qwertyui", "password1"}:
            raise ValueError("That password is too common.")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=128)]


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime


# ── analysis ─────────────────────────────────────────────────────────────────


class AnalyseRequest(BaseModel):
    text: Annotated[str, Field(min_length=1)]
    headline: Annotated[str, Field(max_length=500)] = ""
    source_url: Annotated[str | None, Field(max_length=2048)] = None

    @field_validator("text")
    @classmethod
    def _text_bounds(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < settings.min_text_chars:
            raise ValueError(
                f"Text must be at least {settings.min_text_chars} characters. Got {len(stripped)}."
            )
        if len(stripped) > settings.max_text_chars:
            raise ValueError(
                f"Text must be at most {settings.max_text_chars} characters. Got {len(stripped)}."
            )
        return stripped

    @field_validator("source_url")
    @classmethod
    def _url_scheme(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("source_url must start with http:// or https://")
        return cleaned


class AnalyseUrlRequest(BaseModel):
    url: Annotated[str, Field(min_length=8, max_length=2048)]

    @field_validator("url")
    @classmethod
    def _url_scheme(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return cleaned


class PreviewRequest(BaseModel):
    """Score text without saving it. Used by the live preview in the UI."""

    text: Annotated[str, Field(min_length=1)]
    headline: Annotated[str, Field(max_length=500)] = ""
    source_url: Annotated[str | None, Field(max_length=2048)] = None

    @field_validator("text")
    @classmethod
    def _text_bounds(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < settings.min_text_chars:
            raise ValueError(f"Text must be at least {settings.min_text_chars} characters.")
        if len(stripped) > settings.max_text_chars:
            raise ValueError(f"Text must be at most {settings.max_text_chars} characters.")
        return stripped


class EvidenceResponse(BaseModel):
    label: str
    detail: str
    span: str = ""
    count: int = 1


class SignalResponse(BaseModel):
    id: str
    label: str
    weight: float
    score: float
    summary: str
    applies: bool
    evidence: list[EvidenceResponse]


class BandResponse(BaseModel):
    id: str
    label: str
    description: str


class ConfidenceResponse(BaseModel):
    level: str
    label: str
    reason: str


class StatsResponse(BaseModel):
    word_count: int
    sentence_count: int
    paragraph_count: int
    avg_sentence_words: float
    avg_word_length: float
    unique_word_ratio: float
    exclamation_count: int
    all_caps_count: int
    number_count: int


class AnalysisResult(BaseModel):
    """The full engine output, without any storage identity."""

    score: float
    band: BandResponse
    confidence: ConfidenceResponse
    signals: list[SignalResponse]
    stats: StatsResponse
    source_url: str | None = None


class AnalysisResponse(BaseModel):
    id: int
    title: str
    source_url: str | None
    word_count: int
    score: float
    band: str
    confidence: str
    created_at: datetime
    result: AnalysisResult


class AnalysisSummary(BaseModel):
    """List-view shape: no signal payload, so the list stays small."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_url: str | None
    word_count: int
    score: float
    band: str
    confidence: str
    created_at: datetime


class AnalysisListResponse(BaseModel):
    items: list[AnalysisSummary]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: str
    version: str
    database: str
    url_fetch_enabled: bool


class ErrorResponse(BaseModel):
    detail: str
    code: str | None = None
    extra: dict[str, Any] | None = None
