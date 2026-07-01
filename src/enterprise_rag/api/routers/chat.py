from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from enterprise_rag import schemas
from enterprise_rag.api.dependencies import get_current_user, get_pipeline
from enterprise_rag.db import User, get_db
from enterprise_rag.rag.memory import load_history
from enterprise_rag.rag.pipeline import RagPipeline

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=schemas.ChatResponse)
def send_message(
    request: schemas.ChatRequest,
    user: User = Depends(get_current_user),
    pipeline: RagPipeline = Depends(get_pipeline),
    db: Session = Depends(get_db),
) -> schemas.ChatResponse:
    return pipeline.query(
        db, session_id=request.session_id, message=request.message, user_id=user.id
    )


@router.get("/{session_id}/history", response_model=list[schemas.ChatMessageOut])
def get_chat_history(
    session_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[schemas.ChatMessageOut]:
    return load_history(db, session_id)
