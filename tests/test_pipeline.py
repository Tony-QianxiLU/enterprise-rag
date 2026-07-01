from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.config import Settings
from enterprise_rag.db import Base
from enterprise_rag.providers.embeddings import HashEmbeddingProvider
from enterprise_rag.providers.llm import TemplateLLMProvider
from enterprise_rag.rag.pipeline import RagPipeline
from enterprise_rag.retrieval.retriever import Retriever
from enterprise_rag.retrieval.vector_store import ChromaVectorStore


@pytest.fixture
def db_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def pipeline(tmp_path: Path) -> RagPipeline:
    settings = Settings(
        upload_dir=tmp_path / "uploads",
        chroma_persist_dir=str(tmp_path / "chroma"),
        chunk_size_tokens=50,
        chunk_overlap_tokens=10,
    )
    embedding_provider = HashEmbeddingProvider(dimensions=32)
    llm_provider = TemplateLLMProvider()
    vector_store = ChromaVectorStore(
        persist_dir=settings.chroma_persist_dir, embedding_provider=embedding_provider
    )
    retriever = Retriever(vector_store=vector_store, embedding_provider=embedding_provider)
    return RagPipeline(settings, embedding_provider, llm_provider, vector_store, retriever)


def test_ingest_document_creates_chunks(pipeline: RagPipeline, db_session: Session) -> None:
    text = b"Enterprise RAG platforms combine retrieval with generation for grounded answers."
    document = pipeline.ingest_document(
        db_session, file_bytes=text, filename="notes.txt", uploaded_by="tony@example.com"
    )

    assert document.chunk_count > 0
    assert document.filename == "notes.txt"

    uploaded_path = pipeline._settings.upload_dir / f"{document.id}.txt"
    assert uploaded_path.exists()


def test_query_cites_ingested_document(pipeline: RagPipeline, db_session: Session) -> None:
    text = b"The quarterly compliance report was filed by the finance team in March."
    document = pipeline.ingest_document(
        db_session, file_bytes=text, filename="compliance.txt", uploaded_by="tony@example.com"
    )

    response = pipeline.query(
        db_session,
        session_id=None,
        message="Who filed the quarterly compliance report?",
        user_id="user-1",
    )

    assert response.used_llm is False
    assert len(response.citations) >= 1
    assert any(citation.document_id == document.id for citation in response.citations)


def test_delete_document_removes_citations(pipeline: RagPipeline, db_session: Session) -> None:
    text = b"The quarterly compliance report was filed by the finance team in March."
    document = pipeline.ingest_document(
        db_session, file_bytes=text, filename="compliance.txt", uploaded_by="tony@example.com"
    )

    pipeline.delete_document(db_session, document.id)

    response = pipeline.query(
        db_session,
        session_id=None,
        message="Who filed the quarterly compliance report?",
        user_id="user-1",
    )

    assert all(citation.document_id != document.id for citation in response.citations)


def test_delete_document_removes_uploaded_file(
    pipeline: RagPipeline, db_session: Session
) -> None:
    text = b"The quarterly compliance report was filed by the finance team in March."
    document = pipeline.ingest_document(
        db_session, file_bytes=text, filename="compliance.txt", uploaded_by="tony@example.com"
    )
    uploaded_path = pipeline._settings.upload_dir / f"{document.id}.txt"
    assert uploaded_path.exists()

    pipeline.delete_document(db_session, document.id)

    assert not uploaded_path.exists()


def test_ingest_document_sanitizes_path_traversal_filename(
    pipeline: RagPipeline, db_session: Session
) -> None:
    text = b"Sensitive content that must stay inside the upload directory."
    document = pipeline.ingest_document(
        db_session,
        file_bytes=text,
        filename="../../etc/passwd.txt",
        uploaded_by="tony@example.com",
    )

    uploaded_path = pipeline._settings.upload_dir / f"{document.id}.txt"
    assert uploaded_path.exists()
    assert uploaded_path.resolve().parent == pipeline._settings.upload_dir.resolve()


def test_query_continues_same_session(pipeline: RagPipeline, db_session: Session) -> None:
    pipeline.ingest_document(
        db_session,
        file_bytes=b"The onboarding guide explains benefits enrollment steps.",
        filename="onboarding.txt",
        uploaded_by="tony@example.com",
    )

    first = pipeline.query(
        db_session, session_id=None, message="How do I enroll in benefits?", user_id="user-1"
    )
    second = pipeline.query(
        db_session,
        session_id=first.session_id,
        message="Tell me more about that.",
        user_id="user-1",
    )

    assert second.session_id == first.session_id

    from enterprise_rag.rag.memory import load_history

    history = load_history(db_session, first.session_id, limit=10)
    assert len(history) == 4
