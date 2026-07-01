"""Token-aware chunking, sized against the model's actual context window.

Splitting on tiktoken tokens (rather than words) keeps chunk sizes accurate
for the embedding/LLM context budget, since word count is only a rough proxy
for token count.
"""

import tiktoken

from enterprise_rag.schemas import DocumentChunk, LoadedDocument

_ENCODING = tiktoken.get_encoding("cl100k_base")


def chunk_text(
    text: str,
    *,
    document_id: str,
    source: str,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[DocumentChunk]:
    if chunk_size_tokens <= 0:
        raise ValueError("chunk_size_tokens must be greater than 0")

    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be greater than or equal to 0")

    if overlap_tokens >= chunk_size_tokens:
        raise ValueError("overlap_tokens must be smaller than chunk_size_tokens")

    tokens = _ENCODING.encode(text)
    if not tokens:
        return []

    chunks: list[DocumentChunk] = []
    start = 0
    index = 0
    step = chunk_size_tokens - overlap_tokens

    while start < len(tokens):
        end = min(start + chunk_size_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(
            DocumentChunk(
                id=f"{document_id}:{index}",
                document_id=document_id,
                source=source,
                index=index,
                text=_ENCODING.decode(chunk_tokens),
            )
        )
        index += 1
        start += step

    return chunks


def chunk_document(
    document_id: str,
    document: LoadedDocument,
    *,
    chunk_size_tokens: int,
    overlap_tokens: int,
) -> list[DocumentChunk]:
    return chunk_text(
        document.text,
        document_id=document_id,
        source=document.filename,
        chunk_size_tokens=chunk_size_tokens,
        overlap_tokens=overlap_tokens,
    )
