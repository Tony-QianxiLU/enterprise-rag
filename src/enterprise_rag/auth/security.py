"""Password hashing and JWT access tokens for the auth flow."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from enterprise_rag.config import Settings
from enterprise_rag.schemas import TokenPayload

# bcrypt only uses the first 72 bytes of the input; truncate explicitly so
# behavior is deterministic instead of relying on the library's own handling.
_BCRYPT_MAX_BYTES = 72


def hash_password(password: str) -> str:
    truncated = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(truncated, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    truncated = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(truncated, hashed.encode("utf-8"))


class InvalidTokenError(Exception):
    pass


def create_access_token(*, subject: str, role: str, settings: Settings) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> TokenPayload:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    return TokenPayload.model_validate(payload)
