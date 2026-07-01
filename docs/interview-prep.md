# Interview Preparation

## Recruiter-Friendly Explanation

Enterprise RAG is a multi-user, authenticated document question-answering platform. Users log in, upload PDF/DOCX/PPTX/TXT/Markdown documents, and ask questions that are answered using retrieval-augmented generation, with citations back to the source document. It demonstrates the full applied AI engineering loop at an enterprise-shaped scope: auth and role-based access, document ingestion, chunking, retrieval, answer generation, persisted chat history, an admin dashboard, evaluation, testing, containerized deployment, and documentation.

In simple terms: instead of asking an LLM to answer from memory, the app first retrieves relevant document chunks and then answers using that context -- and unlike a single-user demo, it tracks who uploaded what, who asked what, and gates administrative actions behind a real login and role system.

This project is a direct answer to a question from my earlier [ai-rag-chatbot](https://github.com/Tony-QianxiLU/ai-rag-chatbot) project's own interview prep -- "how would you make this enterprise-ready?" -- which I had answered with "add auth, tenant-aware storage, hybrid retrieval, eval dashboards." This repo adds the auth, structured storage, and eval-report surfacing pieces of that answer; hybrid retrieval and full multi-tenant isolation remain future work (see below).

## Technical Questions

| Question | Strong answer points |
| --- | --- |
| What is RAG? | Retrieval-augmented generation combines search over external knowledge with language generation. The retriever finds relevant context, and the generator uses that context to answer, rather than relying on parametric memory alone. |
| Why chunk documents with tokens instead of words? | Embedding models and LLMs have token-based context budgets, not word-based ones. `chunking.py` uses tiktoken's `cl100k_base` encoding so chunk size and overlap are accurate against the actual model context window, not a rough word-count proxy. |
| Why include citations? | Citations let users inspect sources, debug retrieval quality, and build trust in generated answers. Here they're structured `Citation` objects (document id, source, chunk id, score, preview), not loose strings. |
| Why support local deterministic fallbacks? | `HashEmbeddingProvider` and `TemplateLLMProvider` make demos, tests, evaluation, and CI reliable without depending on paid API calls or external model availability. The provider Protocols mean swapping in the OpenAI-backed implementation is a config change, not a code change. |
| What does the evaluation suite measure? | Retrieval accuracy, citation coverage, groundedness against expected terms, overall pass rate, and latency, computed against a fixture corpus and JSONL benchmark, isolated from the real app's database and vector store. |
| How would you improve retrieval quality? | Add harder eval cases and negative cases, precision/recall@k, hybrid (keyword + vector) retrieval, reranking, metadata filters, and query rewriting -- none of which is implemented yet. |
| How does auth work? | OAuth2 password login (`/auth/login`) verifies a bcrypt hash and issues an HS256 JWT with `sub`, `role`, and expiry claims. Every protected route decodes and validates that token via a FastAPI dependency; admin-only routes layer a role check on top. |

## Architecture Questions

| Question | Strong answer points |
| --- | --- |
| Why separate loader, chunker, retriever, generator, pipeline, and evaluator? | Separation makes each component independently testable, replaceable, and easier to explain or reason about in isolation -- the pipeline module is the only place that wires them together. |
| What happens when `OPENAI_API_KEY` is missing? | The app still runs end to end with local deterministic embeddings and template generation; `used_llm: false` in the chat response signals this to the client. |
| Why is `VectorStore` a Protocol instead of importing Chroma directly everywhere? | It's a deliberate seam: `ChromaVectorStore` is the only implementation today, but a future `PgVectorStore` implementing the same four methods could be substituted in the pipeline's factory function with no changes to the retriever, pipeline, or API layer. |
| Why SQLite instead of Postgres? | SQLite keeps local development and CI dependency-free and fast. `DATABASE_URL` and SQLAlchemy mean the migration to Postgres is designed to be a connection-string change, though that migration itself has not actually been performed yet. |
| Why are FastAPI and Streamlit separate processes talking over HTTP? | The frontend only calls the API via `httpx` with a JWT bearer token -- it never imports the RAG/retrieval/db layers directly. That means any HTTP client (a React app, a mobile client) could reuse the same API today with zero backend changes, and the two processes can scale or deploy independently. |
| Where would you add observability? | Track query text, retrieved chunks and scores, latency, answer metadata, `used_llm`, user feedback, and evaluation results over time -- none of this is wired up yet beyond the evaluation report. |

## System Design Questions

| Question | Strong answer points |
| --- | --- |
| How would you make this enterprise-ready? | This project *is* my answer to that question from the prior single-user chatbot project: it adds JWT auth with role-based access, structured relational storage for users/documents/chat history, an admin stats surface, and a vector store abstraction designed for a pgvector migration. What's still missing: true multi-tenant isolation (a shared collection today, not partitioned per org), hybrid retrieval/reranking, rate limiting, and an actual Postgres/pgvector cutover. |
| How would you handle private documents / multi-tenancy? | Add a `tenant_id` or `organization_id` column to `Document`, `ChatSession`, and vector metadata; filter every query and Chroma `where` clause by it; and enforce it in the FastAPI dependency layer so a JWT claim -- not just role -- scopes every data access. This is designed for but not implemented in the current schema. |
| How would you detect regressions? | Run the offline evaluation suite (`rag-evaluate`) on every PR via GitHub Actions, tracking retrieval accuracy, citation coverage, groundedness, and latency; fail CI if metrics regress below a threshold. |
| How would you scale ingestion? | Move `ingest_document` off the request/response cycle into a background job queue, use durable object storage instead of local `upload_dir`, batch embedding calls, add retry/backoff, and support incremental re-indexing instead of full document replace. |
| How would you fix the chat history endpoint's missing ownership check? | Add a `WHERE ChatSession.user_id == current_user.id` (or admin bypass) check in `GET /chat/{session_id}/history` before returning messages, and return 403/404 instead of the session's contents to any authenticated caller. This is a known, documented gap in the current implementation, not an oversight I'm unaware of. |

## STAR Stories

### Building an Auth-Gated, Multi-User RAG Platform

- Situation: My prior RAG project (ai-rag-chatbot) proved I could build a working retrieval-augmented generation pipeline, but it was single-user with no persistence layer, and its own interview prep flagged "add auth, tenant-aware storage, hybrid retrieval, eval dashboards" as the enterprise-readiness gap.
- Task: Build a second portfolio project that closes part of that gap -- real authentication, structured multi-user persistence, and an admin surface -- on top of the same retrieval/generation core, without pretending to have solved multi-tenancy or hybrid search yet.
- Action: I added a FastAPI backend with OAuth2/JWT login and bcrypt password hashing, SQLAlchemy models for users/documents/chat sessions/messages, role-based access control for admin-only routes, and a `VectorStore` Protocol seam so Chroma could later be swapped for pgvector. I kept the Streamlit frontend fully decoupled, talking to the API only over HTTP.
- Result: A working platform with 51 passing tests, a documented API reference, an offline evaluation suite (5/5 cases passing), and an honest, explicit list of what's still MVP-scoped -- no reranking, no hybrid search, no completed Postgres migration, no multi-tenant isolation, no rate limiting.

### Designing a Swappable Vector Store Boundary

- Situation: Enterprise deployments eventually outgrow a local Chroma directory and need a managed, horizontally scalable vector backend like pgvector, but I didn't want to build that migration before it was needed.
- Task: Design the retrieval layer so that migration is possible later without a rewrite, while shipping something that actually works today.
- Action: I defined `VectorStore` as a `Protocol` with four methods (`add_chunks`, `replace_document_chunks`, `delete_document`, `retrieve`) and implemented `ChromaVectorStore` against the raw `chromadb` client, so the module owns its own metadata schema rather than depending on a framework wrapper's internal assumptions.
- Result: The pipeline, retriever, and API layer depend only on the Protocol, not on Chroma specifically. A `PgVectorStore` implementing the same four methods could be substituted in one factory function (`get_pipeline()`) with no other code changes -- documented explicitly in [docs/architecture.md](architecture.md) as a design decision, not a finished feature.

## Common Follow-Up Questions

- What would happen if a retrieved chunk is irrelevant to the question?
- How would you prevent hallucinated citations?
- How would you evaluate top-k retrieval precision and recall, not just pass/fail?
- How would you choose chunk size and overlap for a new document type?
- How would you handle conflicting information across multiple documents?
- How would you fix the unauthenticated-by-session-id chat history read today?
- What would the first three steps of a real Postgres/pgvector migration look like?
- How would you rate-limit the `/documents` and `/chat` endpoints in production?
