import json
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.api import routers as api_routers
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
def admin_user(db_session: Session) -> User:
    user = User(email="admin@example.com", hashed_password=hash_password("admin-pass"), role="admin")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


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


def test_admin_stats_reflects_documents_and_users(
    client: TestClient, admin_user: User, regular_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        api_routers.admin, "_EVALUATION_REPORT_PATH", Path("nonexistent-report.json")
    )
    admin_token = _login(client, "admin@example.com", "admin-pass")
    user_token = _login(client, "user@example.com", "user-pass")

    client.post(
        "/documents",
        headers=_auth_headers(user_token),
        files={
            "file": (
                "notes.txt",
                b"Enterprise RAG combines retrieval with generation for grounded answers.",
                "text/plain",
            )
        },
    )
    client.post("/chat", headers=_auth_headers(user_token), json={"message": "What is RAG?"})

    response = client.get("/admin/stats", headers=_auth_headers(admin_token))

    assert response.status_code == 200
    body = response.json()
    assert body["user_count"] == 2
    assert body["document_count"] == 1
    assert body["chunk_count"] > 0
    assert body["chat_session_count"] == 1
    assert body["last_evaluation"] is None


def test_admin_stats_includes_last_evaluation_when_report_exists(
    client: TestClient, admin_user: User, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_path = tmp_path / "evaluation-report.json"
    report_path.write_text(
        json.dumps(
            {
                "total_cases": 1,
                "retrieval_accuracy": 1.0,
                "citation_coverage": 1.0,
                "groundedness_rate": 1.0,
                "overall_pass_rate": 1.0,
                "average_latency_ms": 12.5,
                "results": [
                    {
                        "case_id": "case-1",
                        "question": "What is RAG?",
                        "answer": "Retrieval augmented generation.",
                        "citations": ["notes.txt"],
                        "retrieval_passed": True,
                        "citation_passed": True,
                        "groundedness_passed": True,
                        "latency_ms": 12.5,
                    }
                ],
            }
        )
    )
    monkeypatch.setattr(api_routers.admin, "_EVALUATION_REPORT_PATH", report_path)
    admin_token = _login(client, "admin@example.com", "admin-pass")

    response = client.get("/admin/stats", headers=_auth_headers(admin_token))

    assert response.status_code == 200
    last_evaluation = response.json()["last_evaluation"]
    assert last_evaluation is not None
    assert last_evaluation["total_cases"] == 1


def test_admin_stats_requires_admin_role(client: TestClient, regular_user: User) -> None:
    user_token = _login(client, "user@example.com", "user-pass")

    response = client.get("/admin/stats", headers=_auth_headers(user_token))

    assert response.status_code == 403


def test_admin_stats_requires_authentication(client: TestClient) -> None:
    response = client.get("/admin/stats")
    assert response.status_code == 401
