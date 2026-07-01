from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.api.dependencies import get_pipeline
from enterprise_rag.api.main import create_app
from enterprise_rag.auth.security import hash_password
from enterprise_rag.config import Settings
from enterprise_rag.db import Base, User, get_db
from enterprise_rag.providers.embeddings import HashEmbeddingProvider
from enterprise_rag.providers.llm import TemplateLLMProvider
from enterprise_rag.rag.pipeline import RagPipeline
from enterprise_rag.retrieval.retriever import Retriever
from enterprise_rag.retrieval.vector_store import ChromaVectorStore

app = create_app()


@pytest.fixture
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path}/test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
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


@pytest.fixture(autouse=True)
def override_dependencies(db_session: Session, pipeline: RagPipeline) -> Generator[None, None, None]:
    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    def _get_pipeline() -> RagPipeline:
        return pipeline

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_pipeline] = _get_pipeline
    yield
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_pipeline, None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def regular_user(db_session: Session) -> User:
    user = User(email="user@example.com", hashed_password=hash_password("user-pass"), role="user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _login(client: TestClient, email: str, password: str) -> str:
    response = client.post("/auth/login", data={"username": email, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_chat_round_trip_returns_citations(client: TestClient, regular_user: User) -> None:
    token = _login(client, "user@example.com", "user-pass")
    client.post(
        "/documents",
        headers=_auth_headers(token),
        files={
            "file": (
                "compliance.txt",
                b"The quarterly compliance report was filed by the finance team in March.",
                "text/plain",
            )
        },
    )

    response = client.post(
        "/chat",
        headers=_auth_headers(token),
        json={"message": "Who filed the quarterly compliance report?"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["used_llm"] is False
    assert len(body["citations"]) >= 1


def test_chat_history_returns_messages_in_order(client: TestClient, regular_user: User) -> None:
    token = _login(client, "user@example.com", "user-pass")
    client.post(
        "/documents",
        headers=_auth_headers(token),
        files={
            "file": (
                "onboarding.txt",
                b"The onboarding guide explains benefits enrollment steps.",
                "text/plain",
            )
        },
    )

    first_response = client.post(
        "/chat", headers=_auth_headers(token), json={"message": "How do I enroll in benefits?"}
    )
    session_id = first_response.json()["session_id"]

    history_response = client.get(f"/chat/{session_id}/history", headers=_auth_headers(token))

    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


def test_chat_requires_authentication(client: TestClient) -> None:
    response = client.post("/chat", json={"message": "hello"})
    assert response.status_code == 401
