from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from enterprise_rag import schemas
from enterprise_rag.api.dependencies import get_current_user
from enterprise_rag.auth.security import create_access_token, verify_password
from enterprise_rag.config import get_settings
from enterprise_rag.db import User, get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> schemas.Token:
    user = db.query(User).filter(User.email == form_data.username).first()
    if user is None or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    access_token = create_access_token(subject=user.id, role=user.role, settings=settings)
    return schemas.Token(access_token=access_token)


@router.get("/me", response_model=schemas.UserOut)
def read_current_user(user: User = Depends(get_current_user)) -> schemas.UserOut:
    return schemas.UserOut(
        id=user.id,
        email=user.email,
        role=schemas.UserRole(user.role),
        created_at=user.created_at,
    )
