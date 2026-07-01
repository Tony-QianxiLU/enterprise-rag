import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from enterprise_rag import schemas
from enterprise_rag.api.dependencies import get_current_admin
from enterprise_rag.db import ChatSession, Document, User, get_db

router = APIRouter(prefix="/admin", tags=["admin"])

_EVALUATION_REPORT_PATH = Path("reports/evaluation-report.json")


def _load_last_evaluation() -> schemas.EvaluationSummary | None:
    if not _EVALUATION_REPORT_PATH.exists():
        return None
    data = json.loads(_EVALUATION_REPORT_PATH.read_text())
    return schemas.EvaluationSummary.model_validate(data)


@router.get("/stats", response_model=schemas.AdminStats)
def get_admin_stats(
    admin: User = Depends(get_current_admin), db: Session = Depends(get_db)
) -> schemas.AdminStats:
    user_count = db.query(func.count(User.id)).scalar() or 0
    document_count = db.query(func.count(Document.id)).scalar() or 0
    chunk_count = db.query(func.coalesce(func.sum(Document.chunk_count), 0)).scalar() or 0
    chat_session_count = db.query(func.count(ChatSession.id)).scalar() or 0

    return schemas.AdminStats(
        document_count=document_count,
        chunk_count=chunk_count,
        user_count=user_count,
        chat_session_count=chat_session_count,
        last_evaluation=_load_last_evaluation(),
    )
