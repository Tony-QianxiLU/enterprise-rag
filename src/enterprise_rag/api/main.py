"""FastAPI application factory.

Feature routers register themselves in `create_app`. Keep this file thin --
business logic belongs in the router/service modules, not here.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from enterprise_rag.api.routers import admin, auth, chat, documents, health
from enterprise_rag.auth.seed import seed_admin_user
from enterprise_rag.config import get_settings
from enterprise_rag.db import get_session_factory, init_db


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = get_settings()
    init_db()
    session_factory = get_session_factory()
    db = session_factory()
    try:
        seed_admin_user(db, settings)
        db.commit()
    finally:
        db.close()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(documents.router)
    app.include_router(chat.router)
    app.include_router(admin.router)

    return app


app = create_app()
