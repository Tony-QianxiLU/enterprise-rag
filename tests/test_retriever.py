from enterprise_rag.providers.embeddings import HashEmbeddingProvider
from enterprise_rag.retrieval.retriever import Retriever, build_citations
from enterprise_rag.retrieval.vector_store import ChromaVectorStore
from enterprise_rag.schemas import DocumentChunk, RetrievedChunk


def test_retriever_embeds_query_and_returns_matching_chunk(tmp_path) -> None:
    embedder = HashEmbeddingProvider(dimensions=32)
    store = ChromaVectorStore(persist_dir=str(tmp_path / "chroma"), embedding_provider=embedder)
    store.add_chunks(
        [
            DocumentChunk(id="a:0", document_id="doc-a", source="a.txt", index=0, text="RAG retrieval context"),
            DocumentChunk(id="b:0", document_id="doc-b", source="b.txt", index=0, text="unrelated cooking notes"),
        ]
    )

    retriever = Retriever(vector_store=store, embedding_provider=embedder)
    results = retriever.retrieve("RAG retrieval", top_k=1)

    assert len(results) == 1
    assert results[0].chunk.source == "a.txt"


def test_build_citations_truncates_long_preview() -> None:
    long_text = "x" * 200
    retrieved = [
        RetrievedChunk(
            chunk=DocumentChunk(id="a:0", document_id="doc-a", source="a.txt", index=0, text=long_text),
            score=90,
        )
    ]

    citations = build_citations(retrieved)

    assert len(citations) == 1
    citation = citations[0]
    assert citation.document_id == "doc-a"
    assert citation.source == "a.txt"
    assert citation.chunk_id == "a:0"
    assert citation.chunk_index == 0
    assert citation.score == 90
    assert citation.preview == "x" * 160 + "..."
    assert len(citation.preview) == 163


def test_build_citations_does_not_truncate_short_preview() -> None:
    retrieved = [
        RetrievedChunk(
            chunk=DocumentChunk(id="a:0", document_id="doc-a", source="a.txt", index=0, text="short text"),
            score=80,
        )
    ]

    citations = build_citations(retrieved)

    assert citations[0].preview == "short text"
    assert not citations[0].preview.endswith("...")
