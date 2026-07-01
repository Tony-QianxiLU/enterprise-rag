# Deployment

This document is split into two clearly separate parts: how to actually run this project today, and forward-looking cloud deployment guidance that has **not** been implemented yet.

## Running This Today

### Option 1: `uv run` locally

Two processes: the FastAPI backend and the Streamlit frontend, run separately.

```bash
cp .env.example .env

# Terminal 1: backend
PYTHONPATH=src uv run uvicorn enterprise_rag.api.main:app --reload

# Terminal 2: frontend
PYTHONPATH=src uv run streamlit run src/enterprise_rag/frontend/app.py
```

The backend listens on `http://localhost:8000` and initializes its own SQLite database (`data/enterprise_rag.db`) and Chroma persistence directory (`data/chroma`) on first startup, seeding the admin account defined by `ADMIN_EMAIL` / `ADMIN_PASSWORD`. The frontend listens on `http://localhost:8501` and talks to the backend via `API_BASE_URL`.

### Option 2: Docker Compose

This repo ships a real `docker-compose.yml` with two services, built from `docker/Dockerfile.api` and `docker/Dockerfile.frontend`:

```bash
docker compose up --build
```

- `api` builds from `docker/Dockerfile.api` (multi-stage `uv sync --frozen --no-dev` build), exposes port `8000`, loads environment variables from `.env`, and mounts `./data` so SQLite and Chroma state persist across container restarts.
- `frontend` builds from `docker/Dockerfile.frontend`, exposes port `8501`, loads the same `.env`, and depends on `api`.

Both images copy only the synced virtual environment and `src/`, not dev dependencies or tests, keeping the runtime image slim.

This is real, working, local-only deployment tooling. It has not been deployed to any cloud provider.

## Cloud Deployment (Not Yet Done)

The following describes a plausible path to a real cloud deployment. None of it exists today -- no cloud account, container registry, or hosted database has been provisioned for this project. This section is forward-looking guidance, not a claim of a live deployment.

- **API**: push `docker/Dockerfile.api` to a container registry and run it on a container host such as Render, Fly.io, Railway, or AWS ECS/Fargate. Set `DATABASE_URL` to a managed Postgres instance (see below) and `JWT_SECRET` / `ADMIN_PASSWORD` to real secrets via the host's secret manager, not `.env`.
- **Frontend**: either run `docker/Dockerfile.frontend` on the same container host as a second service, or deploy `src/enterprise_rag/frontend/app.py` directly to Streamlit Community Cloud, pointing `API_BASE_URL` at the deployed API's public URL.
- **Database**: migrate `DATABASE_URL` from local SQLite to a managed Postgres instance (e.g. Supabase, Neon, RDS). Per the design in [docs/architecture.md](architecture.md#sqlite-now-postgres-compatible-later-via-database_url), this is intended to be a connection-string change plus adding a Postgres driver dependency, not a schema rewrite -- but it has not actually been done or tested against a real Postgres instance.
- **Vector store**: migrate from the local Chroma persistence directory to either a hosted Chroma instance or a `pgvector`-backed `VectorStore` implementation, per the Protocol seam described in [docs/architecture.md](architecture.md#vectorstore-as-a-deliberate-seam-for-chroma---pgvector). Not yet implemented.
- **CORS**: `cors_allow_origins` in `config.py` currently defaults to `http://localhost:8501` only; a real deployment would need this updated to the deployed frontend's origin.
- **Secrets**: `JWT_SECRET`, `ADMIN_PASSWORD`, and `OPENAI_API_KEY` all currently come from `.env` / environment variables with insecure local defaults (`change-me-in-production`). A cloud deployment must override every one of these via the hosting provider's secret manager before going live.
- **Observability**: no logging, tracing, or monitoring integration exists yet. A real deployment would add structured logging and basic uptime/error monitoring before being considered production-ready.

None of the above is configured in this repository today. Treat it as a roadmap, not a status report.
