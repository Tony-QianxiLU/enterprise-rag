"""Shared FastAPI dependencies: current user/admin resolution and pipeline access."""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from enterprise_rag.auth.security import InvalidTokenError, decode_access_token
from enterprise_rag.config import get_settings
from enterprise_rag.db import User, get_db
from enterprise_rag.rag.pipeline import RagPipeline
from enterprise_rag.rag.pipeline import get_pipeline as _get_pipeline

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    settings = get_settings()
    try:
        payload = decode_access_token(token, settings)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = db.get(User, payload.sub)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


def get_pipeline() -> RagPipeline:
    return _get_pipeline()
