"""Central orchestrator: wires ingestion, retrieval, and generation into one API."""

from functools import lru_cache
from pathlib import Path

from sqlalchemy.orm import Session

from enterprise_rag import schemas
from enterprise_rag.config import Settings, get_settings
from enterprise_rag.db import Document
from enterprise_rag.ingestion.chunking import chunk_document
from enterprise_rag.ingestion.loaders import load_document
from enterprise_rag.providers.embeddings import EmbeddingProvider, build_embedding_provider
from enterprise_rag.providers.llm import LLMProvider, TemplateLLMProvider, build_llm_provider
from enterprise_rag.rag import memory
from enterprise_rag.retrieval.retriever import Retriever, build_citations
from enterprise_rag.retrieval.vector_store import ChromaVectorStore, VectorStore

_SYSTEM_PROMPT = (
    "You are an enterprise assistant answering questions using only the retrieved "
    "document context below. Cite sources by filename and say so if the context is "
    "insufficient to answer."
)


class RagPipeline:
    def __init__(
        self,
        settings: Settings,
        embedding_provider: EmbeddingProvider,
        llm_provider: LLMProvider,
        vector_store: VectorStore,
        retriever: Retriever,
    ) -> None:
        self._settings = settings
        self._embedding_provider = embedding_provider
        self._llm_provider = llm_provider
        self._vector_store = vector_store
        self._retriever = retriever

    def ingest_document(
        self, db: Session, *, file_bytes: bytes, filename: str, uploaded_by: str
    ) -> schemas.DocumentOut:
        loaded = load_document(file_bytes, filename)

        document = Document(
            filename=filename,
            document_type=loaded.document_type.value,
            chunk_count=0,
            uploaded_by=uploaded_by,
        )
        db.add(document)
        db.flush()

        chunks = chunk_document(
            document.id,
            loaded,
            chunk_size_tokens=self._settings.chunk_size_tokens,
            overlap_tokens=self._settings.chunk_overlap_tokens,
        )
        self._vector_store.add_chunks(chunks)
        document.chunk_count = len(chunks)

        upload_dir = self._settings.upload_dir
        upload_dir.mkdir(parents=True, exist_ok=True)
        # Use document.id (not the raw filename) as the on-disk name so a crafted
        # filename like "../../etc/passwd" can never escape upload_dir via path
        # traversal; the original filename is preserved only as metadata.
        extension = Path(filename).suffix
        (upload_dir / f"{document.id}{extension}").write_bytes(file_bytes)

        db.commit()
        db.refresh(document)

        return schemas.DocumentOut(
            id=document.id,
            filename=document.filename,
            document_type=schemas.DocumentType(document.document_type),
            chunk_count=document.chunk_count,
            uploaded_by=document.uploaded_by,
            created_at=document.created_at,
        )

    def list_documents(self, db: Session) -> list[schemas.DocumentOut]:
        documents = db.query(Document).order_by(Document.created_at.desc()).all()
        return [
            schemas.DocumentOut(
                id=document.id,
                filename=document.filename,
                document_type=schemas.DocumentType(document.document_type),
                chunk_count=document.chunk_count,
                uploaded_by=document.uploaded_by,
                created_at=document.created_at,
            )
            for document in documents
        ]

    def delete_document(self, db: Session, document_id: str) -> None:
        document = db.get(Document, document_id)
        if document is None:
            raise ValueError(f"Document '{document_id}' does not exist")

        self._vector_store.delete_document(document_id)

        extension = Path(document.filename).suffix
        upload_path = self._settings.upload_dir / f"{document.id}{extension}"
        upload_path.unlink(missing_ok=True)

        db.delete(document)
        db.commit()

    def query(
        self, db: Session, *, session_id: str | None, message: str, user_id: str
    ) -> schemas.ChatResponse:
        session = memory.get_or_create_session(db, session_id=session_id, user_id=user_id)
        history = memory.load_history(db, session.id)

        retrieved = self._retriever.retrieve(message)
        citations = build_citations(retrieved)

        context = "\n\n".join(
            f"Source: {item.chunk.source}\n{item.chunk.text}" for item in retrieved
        )
        history_text = "\n".join(
            f"{entry.role.value}: {entry.content}" for entry in history
        )

        user_prompt = (
            f"Recent conversation:\n{history_text or '(none)'}\n\n"
            f"Retrieved context:\n{context or '(no relevant context found)'}\n\n"
            f"Question: {message}"
        )

        answer = self._llm_provider.generate(
            system_prompt=_SYSTEM_PROMPT, user_prompt=user_prompt
        )
        used_llm = not isinstance(self._llm_provider, TemplateLLMProvider)

        memory.append_message(db, session.id, schemas.ChatRole.USER, message, [])
        memory.append_message(db, session.id, schemas.ChatRole.ASSISTANT, answer, citations)

        return schemas.ChatResponse(
            session_id=session.id,
            answer=answer,
            citations=citations,
            used_llm=used_llm,
        )


@lru_cache
def get_pipeline() -> RagPipeline:
    settings = get_settings()
    embedding_provider = build_embedding_provider(settings)
    llm_provider = build_llm_provider(settings)
    vector_store = ChromaVectorStore(
        persist_dir=settings.chroma_persist_dir, embedding_provider=embedding_provider
    )
    retriever = Retriever(vector_store=vector_store, embedding_provider=embedding_provider)
    return RagPipeline(settings, embedding_provider, llm_provider, vector_store, retriever)
