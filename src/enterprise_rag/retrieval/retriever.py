"""Query-time retrieval: embeds a question and turns matches into citations."""

from enterprise_rag.providers.embeddings import EmbeddingProvider
from enterprise_rag.retrieval.vector_store import VectorStore
from enterprise_rag.schemas import Citation, RetrievedChunk

_PREVIEW_LENGTH = 160


class Retriever:
    def __init__(self, vector_store: VectorStore, embedding_provider: EmbeddingProvider) -> None:
        self._vector_store = vector_store
        self._embedding_provider = embedding_provider

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        query_embedding = self._embedding_provider.embed_query(query)
        return self._vector_store.retrieve(query_embedding, top_k)


def build_citations(retrieved: list[RetrievedChunk]) -> list[Citation]:
    citations: list[Citation] = []
    for item in retrieved:
        text = item.chunk.text
        preview = text if len(text) <= _PREVIEW_LENGTH else text[:_PREVIEW_LENGTH] + "..."
        citations.append(
            Citation(
                document_id=item.chunk.document_id,
                source=item.chunk.source,
                chunk_id=item.chunk.id,
                chunk_index=item.chunk.index,
                score=item.score,
                preview=preview,
            )
        )
    return citations
