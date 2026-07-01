from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.api.main import create_app
from enterprise_rag.auth.security import hash_password
from enterprise_rag.db import Base, User, get_db

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


@pytest.fixture(autouse=True)
def override_get_db(db_session: Session) -> Generator[None, None, None]:
    def _get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def regular_user(db_session: Session) -> User:
    user = User(email="user@example.com", hashed_password=hash_password("s3cret-pass"), role="user")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def test_login_success_returns_access_token(client: TestClient, regular_user: User) -> None:
    response = client.post(
        "/auth/login", data={"username": "user@example.com", "password": "s3cret-pass"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_login_fails_with_wrong_password(client: TestClient, regular_user: User) -> None:
    response = client.post(
        "/auth/login", data={"username": "user@example.com", "password": "wrong-password"}
    )

    assert response.status_code == 401


def test_login_fails_for_unknown_user(client: TestClient) -> None:
    response = client.post(
        "/auth/login", data={"username": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401


def test_read_current_user_returns_profile(client: TestClient, regular_user: User) -> None:
    login_response = client.post(
        "/auth/login", data={"username": "user@example.com", "password": "s3cret-pass"}
    )
    token = login_response.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["role"] == "user"


def test_protected_route_rejects_missing_token(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_protected_route_rejects_invalid_token(client: TestClient) -> None:
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401
