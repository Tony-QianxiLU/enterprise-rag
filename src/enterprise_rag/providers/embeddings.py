import hashlib
import math
from typing import Protocol

from langchain_openai import OpenAIEmbeddings

from enterprise_rag.config import Settings


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class HashEmbeddingProvider:
    """Deterministic local embeddings for offline development, tests, and CI.

    Not a semantic model -- a stable, dependency-free vector interface so the
    rest of the pipeline (chunking, vector store, retrieval, evaluation) can
    run without a paid API key.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]


class OpenAIEmbeddingProvider:
    def __init__(self, model: str) -> None:
        self._embeddings = OpenAIEmbeddings(model=model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embeddings.embed_query(text)


def build_embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.openai_api_key:
        return OpenAIEmbeddingProvider(model=settings.embedding_model)
    return HashEmbeddingProvider()
