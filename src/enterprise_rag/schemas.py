"""Shared data contracts used across ingestion, retrieval, the RAG pipeline, and the API.

Every feature module should import types from here rather than redefining
similar shapes, so the ingestion -> retrieval -> pipeline -> API chain stays
consistent end to end.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# --- Ingestion -----------------------------------------------------------


class DocumentType(str, Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    MARKDOWN = "markdown"
    PPTX = "pptx"


@dataclass(frozen=True)
class LoadedDocument:
    filename: str
    document_type: DocumentType
    text: str


@dataclass(frozen=True)
class DocumentChunk:
    id: str
    document_id: str
    source: str
    index: int
    text: str

    @property
    def word_count(self) -> int:
        return len(self.text.split())


# --- Retrieval -------------------------------------------------------------


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: DocumentChunk
    score: int  # 0-100, higher is more relevant


@dataclass(frozen=True)
class Citation:
    document_id: str
    source: str
    chunk_id: str
    chunk_index: int
    score: int
    preview: str


@dataclass(frozen=True)
class RagAnswer:
    answer: str
    citations: list[Citation] = field(default_factory=list)
    used_llm: bool = False


# --- Chat / conversation memory -------------------------------------------


class ChatRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessageOut(BaseModel):
    role: ChatRole
    content: str
    citations: list[Citation] = Field(default_factory=list)
    created_at: datetime


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    used_llm: bool = False


# --- Documents API ----------------------------------------------------------


class DocumentOut(BaseModel):
    id: str
    filename: str
    document_type: DocumentType
    chunk_count: int
    uploaded_by: str
    created_at: datetime


class IngestResponse(BaseModel):
    document: DocumentOut
    message: str


# --- Auth --------------------------------------------------------------------


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class UserOut(BaseModel):
    id: str
    email: str
    role: UserRole
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str
    role: UserRole
    exp: datetime


# --- Evaluation ----------------------------------------------------------------


class EvaluationCase(BaseModel):
    id: str
    question: str
    expected_source: str
    expected_terms: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    case_id: str
    question: str
    answer: str
    citations: list[str]
    retrieval_passed: bool
    citation_passed: bool
    groundedness_passed: bool
    latency_ms: float


class EvaluationSummary(BaseModel):
    total_cases: int
    retrieval_accuracy: float
    citation_coverage: float
    groundedness_rate: float
    overall_pass_rate: float
    average_latency_ms: float
    results: list[EvaluationResult]


# --- Admin dashboard ------------------------------------------------------------


class AdminStats(BaseModel):
    document_count: int
    chunk_count: int
    user_count: int
    chat_session_count: int
    last_evaluation: EvaluationSummary | None = None
