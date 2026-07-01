"""SQLAlchemy setup for relational state: users, documents, chat sessions/messages.

Chunk vectors live in the vector store (Chroma today, pgvector-compatible
later), not here. This file only tracks metadata and structured records that
the admin dashboard and chat history need to query relationally.

Defaults to local SQLite (`DATABASE_URL`). Swapping to Postgres is a
connection-string change; no ORM code here is SQLite-specific.
"""

import uuid
from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from enterprise_rag.config import get_settings


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chat_sessions: Mapped[list["ChatSession"]] = relationship(back_populates="user")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    filename: Mapped[str] = mapped_column(String(512))
    document_type: Mapped[str] = mapped_column(String(20))
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


_engine = None
_SessionLocal: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
        _engine = create_engine(settings.database_url, connect_args=connect_args)
    return _engine


def get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()
