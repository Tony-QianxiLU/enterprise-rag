"""Seeds the initial admin user so the platform is usable on first boot."""

from sqlalchemy.orm import Session

from enterprise_rag.auth.security import hash_password
from enterprise_rag.config import Settings, get_settings
from enterprise_rag.db import User, get_session_factory, init_db


def seed_admin_user(db: Session, settings: Settings) -> None:
    existing = db.query(User).filter(User.email == settings.admin_email).first()
    if existing is not None:
        return
    admin = User(
        email=settings.admin_email,
        hashed_password=hash_password(settings.admin_password),
        role="admin",
    )
    db.add(admin)


def main() -> None:
    init_db()
    session_factory = get_session_factory()
    db = session_factory()
    try:
        settings = get_settings()
        seed_admin_user(db, settings)
        db.commit()
        print(f"Admin user ready: {settings.admin_email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
