"""FastAPI application factory.

Feature routers register themselves in `create_app`. Keep this file thin --
business logic belongs in the router/service modules, not here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from enterprise_rag.api.routers import health
from enterprise_rag.config import get_settings
from enterprise_rag.db import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)

    @app.on_event("startup")
    def on_startup() -> None:
        init_db()

    return app


app = create_app()
