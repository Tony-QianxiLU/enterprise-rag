import pytest

from enterprise_rag.ingestion.chunking import chunk_document, chunk_text
from enterprise_rag.schemas import DocumentType, LoadedDocument


def test_chunk_text_splits_tokens_with_overlap() -> None:
    text = "one two three four five six seven eight nine ten"

    chunks = chunk_text(
        text,
        document_id="doc-1",
        source="notes.txt",
        chunk_size_tokens=4,
        overlap_tokens=1,
    )

    assert [chunk.text for chunk in chunks] == [
        "one two three four",
        " four five six seven",
        " seven eight nine ten",
        " ten",
    ]
    assert chunks[0].id == "doc-1:0"
    assert chunks[0].document_id == "doc-1"
    assert chunks[0].source == "notes.txt"
    assert [chunk.index for chunk in chunks] == [0, 1, 2, 3]
    assert [chunk.id for chunk in chunks] == ["doc-1:0", "doc-1:1", "doc-1:2", "doc-1:3"]


def test_chunk_text_no_overlap_produces_disjoint_chunks() -> None:
    text = "one two three four five six"

    chunks = chunk_text(
        text,
        document_id="doc-2",
        source="notes.txt",
        chunk_size_tokens=3,
        overlap_tokens=0,
    )

    assert len(chunks) == 2
    assert chunks[0].text == "one two three"
    assert chunks[1].text == " four five six"


def test_chunk_text_empty_string_returns_no_chunks() -> None:
    chunks = chunk_text(
        "",
        document_id="doc-3",
        source="empty.txt",
        chunk_size_tokens=10,
        overlap_tokens=0,
    )

    assert chunks == []


def test_chunk_document_uses_filename_as_source() -> None:
    document = LoadedDocument(
        filename="report.pdf",
        document_type=DocumentType.PDF,
        text="alpha beta gamma delta",
    )

    chunks = chunk_document("doc-4", document, chunk_size_tokens=2, overlap_tokens=0)

    assert [chunk.source for chunk in chunks] == ["report.pdf", "report.pdf"]
    assert [chunk.document_id for chunk in chunks] == ["doc-4", "doc-4"]


def test_chunk_text_rejects_non_positive_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_size_tokens must be greater than 0"):
        chunk_text(
            "hello world",
            document_id="doc-5",
            source="a.txt",
            chunk_size_tokens=0,
            overlap_tokens=0,
        )


def test_chunk_text_rejects_overlap_not_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError, match="overlap_tokens must be smaller than chunk_size_tokens"):
        chunk_text(
            "hello world",
            document_id="doc-6",
            source="a.txt",
            chunk_size_tokens=10,
            overlap_tokens=10,
        )


def test_chunk_text_rejects_negative_overlap() -> None:
    with pytest.raises(ValueError, match="overlap_tokens must be greater than or equal to 0"):
        chunk_text(
            "hello world",
            document_id="doc-7",
            source="a.txt",
            chunk_size_tokens=10,
            overlap_tokens=-1,
        )
