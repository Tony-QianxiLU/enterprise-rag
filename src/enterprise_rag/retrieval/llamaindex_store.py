"""Alternative VectorStore backend built on LlamaIndex's indexing APIs.

ChromaVectorStore (vector_store.py) talks to Chroma directly and is what
get_pipeline() wires up by default. This module implements the same
VectorStore Protocol using llama-index-vector-stores-chroma instead, so the
two frameworks can be compared on equal footing and swapped without touching
the pipeline, retriever, or API layer. Embeddings still come from this
project's own EmbeddingProvider (not LlamaIndex's embedding abstraction) --
LlamaIndex is used here for its indexing/node model, not to replace the
embedding layer.
"""

import chromadb
from chromadb.config import Settings
from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode
from llama_index.core.vector_stores.types import VectorStoreQuery
from llama_index.vector_stores.chroma import ChromaVectorStore as LlamaChromaVectorStore

from enterprise_rag.providers.embeddings import EmbeddingProvider
from enterprise_rag.schemas import DocumentChunk, RetrievedChunk


class LlamaIndexVectorStore:
    def __init__(
        self,
        persist_dir: str,
        embedding_provider: EmbeddingProvider,
        collection_name: str = "documents_llamaindex",
    ) -> None:
        self._embedding_provider = embedding_provider
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        collection = self._client.get_or_create_collection(name=collection_name)
        self._vector_store = LlamaChromaVectorStore(chroma_collection=collection)

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return

        embeddings = self._embedding_provider.embed_documents([chunk.text for chunk in chunks])
        nodes = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            # "document_id" is reserved by LlamaIndex's own metadata serialization
            # (derived from ref_doc_id below) -- setting it as a plain metadata key
            # would silently get overwritten, so the document/source/index the
            # store needs to reconstruct a DocumentChunk live on the relationship
            # (document_id) and plain metadata (source, index) respectively.
            node = TextNode(
                id_=chunk.id,
                text=chunk.text,
                metadata={"source": chunk.source, "index": chunk.index},
                embedding=embedding,
            )
            node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(
                node_id=chunk.document_id
            )
            nodes.append(node)
        self._vector_store.add(nodes)

    def replace_document_chunks(self, document_id: str, chunks: list[DocumentChunk]) -> None:
        self.delete_document(document_id)
        self.add_chunks(chunks)

    def delete_document(self, document_id: str) -> None:
        self._vector_store.delete(ref_doc_id=document_id)

    def retrieve(self, query_embedding: list[float], top_k: int) -> list[RetrievedChunk]:
        result = self._vector_store.query(
            VectorStoreQuery(query_embedding=query_embedding, similarity_top_k=top_k)
        )

        retrieved: list[RetrievedChunk] = []
        nodes = result.nodes or []
        similarities = result.similarities or [0.0] * len(nodes)
        for node, similarity in zip(nodes, similarities, strict=True):
            chunk = DocumentChunk(
                id=node.node_id,
                document_id=str(node.ref_doc_id),
                source=str(node.metadata["source"]),
                index=int(node.metadata["index"]),
                text=node.get_content(),
            )
            score = max(0, min(100, int(round(similarity * 100))))
            retrieved.append(RetrievedChunk(chunk=chunk, score=score))

        return retrieved
