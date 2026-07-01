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


def test_upload_document_returns_ingest_response(
    client: TestClient, regular_user: User
) -> None:
    token = _login(client, "user@example.com", "user-pass")
    file_content = b"Enterprise RAG combines retrieval with generation for grounded answers."

    response = client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("notes.txt", file_content, "text/plain")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["document"]["filename"] == "notes.txt"
    assert body["document"]["chunk_count"] > 0


def test_list_documents_returns_uploaded_document(
    client: TestClient, regular_user: User
) -> None:
    token = _login(client, "user@example.com", "user-pass")
    file_content = b"The quarterly compliance report was filed by the finance team in March."
    client.post(
        "/documents",
        headers=_auth_headers(token),
        files={"file": ("compliance.txt", file_content, "text/plain")},
    )

    response = client.get("/documents", headers=_auth_headers(token))

    assert response.status_code == 200
    documents = response.json()
    assert len(documents) == 1
    assert documents[0]["filename"] == "compliance.txt"


def test_delete_document_requires_admin(
    client: TestClient, regular_user: User, admin_user: User
) -> None:
    admin_token = _login(client, "admin@example.com", "admin-pass")
    user_token = _login(client, "user@example.com", "user-pass")

    upload_response = client.post(
        "/documents",
        headers=_auth_headers(admin_token),
        files={"file": ("policy.txt", b"Company policy on expense reports.", "text/plain")},
    )
    document_id = upload_response.json()["document"]["id"]

    forbidden_response = client.delete(f"/documents/{document_id}", headers=_auth_headers(user_token))
    assert forbidden_response.status_code == 403

    admin_response = client.delete(f"/documents/{document_id}", headers=_auth_headers(admin_token))
    assert admin_response.status_code == 204

    list_response = client.get("/documents", headers=_auth_headers(admin_token))
    assert list_response.json() == []


def test_delete_unknown_document_returns_404(
    client: TestClient, admin_user: User
) -> None:
    admin_token = _login(client, "admin@example.com", "admin-pass")

    response = client.delete("/documents/does-not-exist", headers=_auth_headers(admin_token))

    assert response.status_code == 404


def test_documents_require_authentication(client: TestClient) -> None:
    response = client.get("/documents")
    assert response.status_code == 401
