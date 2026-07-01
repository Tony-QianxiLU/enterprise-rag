from pathlib import Path

import pytest

from enterprise_rag.auth.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from enterprise_rag.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        data_dir=tmp_path,
        database_url=f"sqlite:///{tmp_path}/test.db",
        chroma_persist_dir=str(tmp_path / "chroma"),
        upload_dir=tmp_path / "uploads",
    )


def test_hash_and_verify_password_round_trip() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert hashed != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", hashed)


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct-horse-battery-staple")
    assert not verify_password("wrong-password", hashed)


def test_create_and_decode_access_token_round_trip(settings: Settings) -> None:
    token = create_access_token(subject="user@example.com", role="admin", settings=settings)
    payload = decode_access_token(token, settings)
    assert payload.sub == "user@example.com"
    assert payload.role == "admin"


def test_decode_tampered_token_raises_invalid_token_error(settings: Settings) -> None:
    token = create_access_token(subject="user@example.com", role="user", settings=settings)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered, settings)


def test_decode_expired_token_raises_invalid_token_error(settings: Settings) -> None:
    settings.access_token_expire_minutes = -1
    token = create_access_token(subject="user@example.com", role="user", settings=settings)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)
