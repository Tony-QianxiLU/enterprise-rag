# API Reference

Base URL (local default): `http://localhost:8000`

All authenticated endpoints expect a JWT bearer token obtained from `POST /auth/login`:

```text
Authorization: Bearer <access_token>
```

## Endpoint Summary

| Method | Path | Auth required | Description |
| --- | --- | --- | --- |
| `POST` | `/auth/login` | No | OAuth2 password login (username=email, password); returns a bearer JWT. 401 on bad credentials. |
| `GET` | `/auth/me` | Yes | Returns the authenticated user's profile. |
| `POST` | `/documents` | Yes | Uploads a file, ingests it through the RAG pipeline (chunk + embed + store). 201 on success. |
| `GET` | `/documents` | Yes | Lists all ingested documents. |
| `DELETE` | `/documents/{document_id}` | Yes (admin only) | Deletes a document and its vectors. 204 on success, 404 if the id is unknown, 403 for non-admins. |
| `POST` | `/chat` | Yes | Sends a chat message, runs retrieval + generation, persists history, returns citations. |
| `GET` | `/chat/{session_id}/history` | Yes | Returns chronological chat history for a session. Note: no ownership check ties `session_id` to the requesting user. |
| `GET` | `/admin/stats` | Yes (admin only) | Returns platform stats: user/document/chat-session counts, total chunk count, and the last evaluation summary if present. |
| `GET` | `/health` | No | Liveness check. Returns `{"status": "ok"}`. |

## `POST /auth/login`

Auth required: No.

OAuth2 password flow. Body is `application/x-www-form-urlencoded` (standard `OAuth2PasswordRequestForm`), not JSON: `username` is the user's email, `password` is their password.

Request:

```text
username=admin@example.com&password=change-me-in-production
```

Response `200` (`schemas.Token`):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Response `401`: incorrect email or password.

## `GET /auth/me`

Auth required: Yes.

Response `200` (`schemas.UserOut`):

```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "admin@example.com",
  "role": "admin",
  "created_at": "2026-07-01T12:00:00Z"
}
```

## `POST /documents`

Auth required: Yes.

`multipart/form-data` upload with a single `file` field. Supported extensions: `.pdf`, `.docx`, `.pptx`, `.txt`, `.md`, `.markdown`.

Response `201` (`schemas.IngestResponse`):

```json
{
  "document": {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "filename": "employee-onboarding.pdf",
    "document_type": "pdf",
    "chunk_count": 4,
    "uploaded_by": "admin@example.com",
    "created_at": "2026-07-01T12:01:00Z"
  },
  "message": "Document ingested successfully"
}
```

## `GET /documents`

Auth required: Yes.

Response `200` (`list[schemas.DocumentOut]`):

```json
[
  {
    "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "filename": "employee-onboarding.pdf",
    "document_type": "pdf",
    "chunk_count": 4,
    "uploaded_by": "admin@example.com",
    "created_at": "2026-07-01T12:01:00Z"
  }
]
```

## `DELETE /documents/{document_id}`

Auth required: Yes, admin only.

Deletes the document's relational record and its vectors from the vector store.

- `204 No Content` on success.
- `404 Not Found` if `document_id` is unknown.
- `403 Forbidden` if the caller is not an admin.

## `POST /chat`

Auth required: Yes.

Request (`schemas.ChatRequest`):

```json
{
  "session_id": null,
  "message": "When can a new employee enroll in health benefits?"
}
```

Pass an existing `session_id` to continue a conversation with prior context; omit or pass `null` to start a new session.

Response `200` (`schemas.ChatResponse`):

```json
{
  "session_id": "b3f1c9de-1234-4a5b-9c6d-7e8f9a0b1c2d",
  "answer": "New employees may enroll in health benefits within 30 days of their start date through the benefits enrollment portal. Source: employee-onboarding.txt",
  "citations": [
    {
      "document_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
      "source": "employee-onboarding.txt",
      "chunk_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7:0",
      "chunk_index": 0,
      "score": 87,
      "preview": "Employee Onboarding Guide. New hires must complete identity verification and laptop setup..."
    }
  ],
  "used_llm": false
}
```

`used_llm` is `false` when `OPENAI_API_KEY` is not configured and the deterministic `TemplateLLMProvider` fallback answered instead.

## `GET /chat/{session_id}/history`

Auth required: Yes.

Response `200` (`list[schemas.ChatMessageOut]`):

```json
[
  {
    "role": "user",
    "content": "When can a new employee enroll in health benefits?",
    "citations": [],
    "created_at": "2026-07-01T12:02:00Z"
  },
  {
    "role": "assistant",
    "content": "New employees may enroll in health benefits within 30 days...",
    "citations": [
      {
        "document_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "source": "employee-onboarding.txt",
        "chunk_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7:0",
        "chunk_index": 0,
        "score": 87,
        "preview": "Employee Onboarding Guide. New hires must complete identity verification and laptop setup..."
      }
    ],
    "created_at": "2026-07-01T12:02:01Z"
  }
]
```

Known limitation: this endpoint does not verify that `session_id` belongs to the requesting user -- any authenticated user can currently read any session's history by id. See [README.md Future Improvements](../README.md#future-improvements).

## `GET /admin/stats`

Auth required: Yes, admin only.

Response `200` (`schemas.AdminStats`):

```json
{
  "document_count": 5,
  "chunk_count": 23,
  "user_count": 3,
  "chat_session_count": 7,
  "last_evaluation": {
    "total_cases": 5,
    "retrieval_accuracy": 1.0,
    "citation_coverage": 1.0,
    "groundedness_rate": 1.0,
    "overall_pass_rate": 1.0,
    "average_latency_ms": 5.6,
    "results": [
      {
        "case_id": "onboarding-benefits",
        "question": "When can a new employee enroll in health benefits?",
        "answer": "...",
        "citations": ["employee-onboarding.txt", "product-faq.txt"],
        "retrieval_passed": true,
        "citation_passed": true,
        "groundedness_passed": true,
        "latency_ms": 9.3
      }
    ]
  }
}
```

`last_evaluation` is `null` if `reports/evaluation-report.json` does not exist yet (i.e. `rag-evaluate` has never been run).

## `GET /health`

Auth required: No.

Response `200`:

```json
{
  "status": "ok"
}
```
