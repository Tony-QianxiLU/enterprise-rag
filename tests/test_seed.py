from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from enterprise_rag.auth.seed import seed_admin_user
from enterprise_rag.config import Settings
from enterprise_rag.db import Base, User


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path}/test.db",
        chroma_persist_dir=str(tmp_path / "chroma"),
        upload_dir=tmp_path / "uploads",
        admin_email="admin@example.com",
        admin_password="s3cret-password",
    )


@pytest.fixture
def db_session(tmp_path: Path) -> Generator[Session, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path}/seed_test.db", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_seed_admin_user_creates_exactly_one_admin(db_session: Session, settings: Settings) -> None:
    seed_admin_user(db_session, settings)
    db_session.commit()

    users = db_session.query(User).all()
    assert len(users) == 1
    assert users[0].email == settings.admin_email
    assert users[0].role == "admin"


def test_seed_admin_user_is_idempotent(db_session: Session, settings: Settings) -> None:
    seed_admin_user(db_session, settings)
    db_session.commit()
    first_id = db_session.query(User).one().id

    seed_admin_user(db_session, settings)
    db_session.commit()

    users = db_session.query(User).all()
    assert len(users) == 1
    assert users[0].id == first_id
