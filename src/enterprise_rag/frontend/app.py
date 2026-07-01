"""Streamlit frontend for the Enterprise RAG platform.

Talks to the FastAPI backend over HTTP only -- no direct imports from the
rag/retrieval/db layers, so this process can be deployed independently of
the API.
"""

import httpx
import streamlit as st

from enterprise_rag import schemas
from enterprise_rag.config import get_settings

st.set_page_config(page_title="Enterprise RAG", page_icon="RAG", layout="wide")

settings = get_settings()

if "token" not in st.session_state:
    st.session_state.token = None
if "role" not in st.session_state:
    st.session_state.role = None
if "email" not in st.session_state:
    st.session_state.email = None
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def login(email: str, password: str) -> str | None:
    try:
        response = httpx.post(
            f"{settings.api_base_url}/auth/login",
            data={"username": email, "password": password},
        )
    except httpx.HTTPError as exc:
        return f"Could not reach the API: {exc}"

    if response.status_code != 200:
        return "Incorrect email or password."

    token = schemas.Token.model_validate(response.json())

    me_response = httpx.get(
        f"{settings.api_base_url}/auth/me",
        headers={"Authorization": f"Bearer {token.access_token}"},
    )
    if me_response.status_code != 200:
        return "Login succeeded but the profile lookup failed."

    user = schemas.UserOut.model_validate(me_response.json())
    st.session_state.token = token.access_token
    st.session_state.role = user.role.value
    st.session_state.email = user.email
    return None


def logout() -> None:
    st.session_state.token = None
    st.session_state.role = None
    st.session_state.email = None
    st.session_state.session_id = None
    st.session_state.chat_history = []


def render_login() -> None:
    st.title("Enterprise RAG")
    st.subheader("Sign in")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        error = login(email, password)
        if error:
            st.error(error)
        else:
            st.rerun()


def render_upload_section() -> None:
    st.subheader("Documents")
    uploaded_file = st.file_uploader("Upload a document", type=["pdf", "docx", "txt", "md", "pptx"])
    if uploaded_file is not None and st.button("Ingest document"):
        files = {"file": (uploaded_file.name, uploaded_file.getvalue())}
        response = httpx.post(
            f"{settings.api_base_url}/documents",
            files=files,
            headers=auth_headers(),
            timeout=120,
        )
        if response.status_code == 201:
            ingest = schemas.IngestResponse.model_validate(response.json())
            st.success(ingest.message)
        else:
            st.error(f"Upload failed: {response.text}")

    list_response = httpx.get(f"{settings.api_base_url}/documents", headers=auth_headers())
    if list_response.status_code != 200:
        st.error("Could not load documents.")
        return

    documents = [schemas.DocumentOut.model_validate(item) for item in list_response.json()]
    if not documents:
        st.caption("No documents ingested yet.")
        return

    for document in documents:
        st.write(
            f"{document.filename} -- {document.document_type.value} -- "
            f"{document.chunk_count} chunks -- uploaded by {document.uploaded_by}"
        )


def render_citation(citation: schemas.Citation) -> None:
    with st.expander(f"{citation.source} (score {citation.score})"):
        st.caption(f"Chunk {citation.chunk_index} -- {citation.chunk_id}")
        st.write(citation.preview)


def render_chat_section() -> None:
    st.subheader("Chat")
    for turn in st.session_state.chat_history:
        with st.chat_message(turn["role"]):
            st.write(turn["content"])
            for citation in turn.get("citations", []):
                render_citation(citation)

    message = st.chat_input("Ask a question about your documents")
    if not message:
        return

    st.session_state.chat_history.append({"role": "user", "content": message, "citations": []})

    request = schemas.ChatRequest(session_id=st.session_state.session_id, message=message)
    response = httpx.post(
        f"{settings.api_base_url}/chat",
        json=request.model_dump(),
        headers=auth_headers(),
        timeout=120,
    )
    if response.status_code != 200:
        st.error(f"Chat request failed: {response.text}")
        return

    chat_response = schemas.ChatResponse.model_validate(response.json())
    st.session_state.session_id = chat_response.session_id
    st.session_state.chat_history.append(
        {
            "role": "assistant",
            "content": chat_response.answer,
            "citations": chat_response.citations,
        }
    )
    st.rerun()


def render_app() -> None:
    with st.sidebar:
        st.write(f"Signed in as **{st.session_state.email}** ({st.session_state.role})")
        if st.button("Log out"):
            logout()
            st.rerun()

    st.title("Enterprise RAG")
    render_upload_section()
    st.divider()
    render_chat_section()


if st.session_state.token is None:
    render_login()
else:
    render_app()
