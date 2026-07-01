from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from enterprise_rag import schemas
from enterprise_rag.api.dependencies import get_current_admin, get_current_user, get_pipeline
from enterprise_rag.db import User, get_db
from enterprise_rag.rag.pipeline import RagPipeline

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", response_model=schemas.IngestResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile,
    user: User = Depends(get_current_user),
    pipeline: RagPipeline = Depends(get_pipeline),
    db: Session = Depends(get_db),
) -> schemas.IngestResponse:
    file_bytes = await file.read()
    document = pipeline.ingest_document(
        db, file_bytes=file_bytes, filename=file.filename or "upload", uploaded_by=user.email
    )
    return schemas.IngestResponse(document=document, message="Document ingested successfully")


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(
    user: User = Depends(get_current_user),
    pipeline: RagPipeline = Depends(get_pipeline),
    db: Session = Depends(get_db),
) -> list[schemas.DocumentOut]:
    return pipeline.list_documents(db)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: str,
    admin: User = Depends(get_current_admin),
    pipeline: RagPipeline = Depends(get_pipeline),
    db: Session = Depends(get_db),
) -> None:
    try:
        pipeline.delete_document(db, document_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
