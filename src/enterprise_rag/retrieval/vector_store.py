"""Vector store abstraction over Chroma, kept swappable for a future pgvector backend.

Uses the raw chromadb client directly (not the LangChain/LlamaIndex wrappers) so this
module owns the exact metadata schema and stays a thin, dependency-light Protocol
implementation.
"""

from typing import Protocol

import chromadb
from chromadb.config import Settings

from enterprise_rag.providers.embeddings import EmbeddingProvider
from enterprise_rag.schemas import DocumentChunk, RetrievedChunk


class VectorStore(Protocol):
    def add_chunks(self, chunks: list[DocumentChunk]) -> None: ...

    def replace_document_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> None: ...

    def delete_document(self, document_id: str) -> None: ...

    def retrieve(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]: ...


class ChromaVectorStore:
    def __init__(
        self,
        persist_dir: str,
        embedding_provider: EmbeddingProvider,
        collection_name: str = "documents",
    ) -> None:
        self._embedding_provider = embedding_provider
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(name=collection_name)

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return

        texts = [chunk.text for chunk in chunks]
        embeddings = self._embedding_provider.embed_documents(texts)
        self._collection.upsert(
            ids=[chunk.id for chunk in chunks],
            documents=texts,
            metadatas=[
                {
                    "document_id": chunk.document_id,
                    "source": chunk.source,
                    "index": chunk.index,
                }
                for chunk in chunks
            ],
            embeddings=embeddings,
        )

    def replace_document_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> None:
        self.delete_document(document_id)
        self.add_chunks(chunks)

    def delete_document(self, document_id: str) -> None:
        self._collection.delete(where={"document_id": document_id})

    def retrieve(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        retrieved: list[RetrievedChunk] = []
        for chunk_id, document, metadata, distance in zip(
            ids,
            documents,
            metadatas,
            distances,
            strict=True,
        ):
            chunk = DocumentChunk(
                id=chunk_id,
                document_id=str(metadata["document_id"]),
                source=str(metadata["source"]),
                index=int(metadata["index"]),
                text=document,
            )
            score = max(0, int(round((1 - float(distance)) * 100)))
            retrieved.append(RetrievedChunk(chunk=chunk, score=score))

        return retrieved
