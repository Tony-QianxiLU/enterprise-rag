"""Chat session persistence: sessions and messages are relational, vectors are not."""

import dataclasses
import json

from sqlalchemy.orm import Session

from enterprise_rag import schemas
from enterprise_rag.db import ChatMessage, ChatSession, new_id


def get_or_create_session(db: Session, *, session_id: str | None, user_id: str) -> ChatSession:
    if session_id is not None:
        existing = db.get(ChatSession, session_id)
        if existing is not None:
            return existing

    session = ChatSession(id=session_id or new_id(), user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def load_history(db: Session, session_id: str, limit: int = 10) -> list[schemas.ChatMessageOut]:
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )

    history = [
        schemas.ChatMessageOut(
            role=schemas.ChatRole(message.role),
            content=message.content,
            citations=[schemas.Citation(**d) for d in json.loads(message.citations_json)],
            created_at=message.created_at,
        )
        for message in messages
    ]
    history.reverse()
    return history


def append_message(
    db: Session,
    session_id: str,
    role: schemas.ChatRole,
    content: str,
    citations: list[schemas.Citation],
) -> None:
    message = ChatMessage(
        session_id=session_id,
        role=role.value,
        content=content,
        citations_json=json.dumps([dataclasses.asdict(citation) for citation in citations]),
    )
    db.add(message)
    db.commit()
