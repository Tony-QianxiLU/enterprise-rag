from enterprise_rag.providers.embeddings import HashEmbeddingProvider
from enterprise_rag.retrieval.llamaindex_store import LlamaIndexVectorStore
from enterprise_rag.schemas import DocumentChunk


def _make_store(tmp_path) -> LlamaIndexVectorStore:
    return LlamaIndexVectorStore(
        persist_dir=str(tmp_path / "chroma"),
        embedding_provider=HashEmbeddingProvider(dimensions=32),
    )


def test_add_and_retrieve_returns_the_right_chunk(tmp_path) -> None:
    store = _make_store(tmp_path)
    chunks = [
        DocumentChunk(id="a:0", document_id="doc-a", source="a.txt", index=0, text="RAG retrieval context"),
        DocumentChunk(id="b:0", document_id="doc-b", source="b.txt", index=0, text="unrelated cooking notes"),
    ]

    store.add_chunks(chunks)
    embedding = HashEmbeddingProvider(dimensions=32).embed_query("RAG retrieval")
    results = store.retrieve(embedding, top_k=1)

    assert len(results) == 1
    assert results[0].chunk.id == "a:0"
    assert results[0].chunk.document_id == "doc-a"
    assert results[0].chunk.source == "a.txt"


def test_replace_document_chunks_removes_old_chunks(tmp_path) -> None:
    store = _make_store(tmp_path)
    embedder = HashEmbeddingProvider(dimensions=32)

    store.add_chunks(
        [DocumentChunk(id="a:0", document_id="doc-a", source="a.txt", index=0, text="original content")]
    )
    store.replace_document_chunks(
        "doc-a",
        [DocumentChunk(id="a:1", document_id="doc-a", source="a-v2.txt", index=0, text="updated content")],
    )

    results = store.retrieve(embedder.embed_query("original content"), top_k=10)
    ids = [item.chunk.id for item in results]

    assert "a:0" not in ids
    assert "a:1" in ids


def test_delete_document_removes_only_that_documents_chunks(tmp_path) -> None:
    store = _make_store(tmp_path)
    embedder = HashEmbeddingProvider(dimensions=32)

    store.add_chunks(
        [
            DocumentChunk(id="a:0", document_id="doc-a", source="a.txt", index=0, text="alpha content"),
            DocumentChunk(id="b:0", document_id="doc-b", source="b.txt", index=0, text="beta content"),
        ]
    )

    store.delete_document("doc-a")

    results = store.retrieve(embedder.embed_query("alpha beta content"), top_k=10)
    document_ids = {item.chunk.document_id for item in results}

    assert document_ids == {"doc-b"}
