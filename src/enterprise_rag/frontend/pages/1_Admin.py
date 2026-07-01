"""Admin dashboard: stats, last evaluation summary, and document management."""

import httpx
import streamlit as st

from enterprise_rag import schemas
from enterprise_rag.config import get_settings

st.set_page_config(page_title="Admin | Enterprise RAG", page_icon="RAG", layout="wide")

settings = get_settings()


def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {st.session_state.token}"}


def render_evaluation_summary(summary: schemas.EvaluationSummary) -> None:
    st.subheader("Last Evaluation")
    cols = st.columns(4)
    cols[0].metric("Retrieval accuracy", f"{summary.retrieval_accuracy:.0%}")
    cols[1].metric("Citation coverage", f"{summary.citation_coverage:.0%}")
    cols[2].metric("Groundedness rate", f"{summary.groundedness_rate:.0%}")
    cols[3].metric("Overall pass rate", f"{summary.overall_pass_rate:.0%}")
    st.caption(f"{summary.total_cases} cases, average latency {summary.average_latency_ms:.0f} ms")


def render_documents(documents: list[schemas.DocumentOut]) -> None:
    st.subheader("Documents")
    if not documents:
        st.caption("No documents ingested yet.")
        return

    for document in documents:
        columns = st.columns([4, 2, 2, 2, 1])
        columns[0].write(document.filename)
        columns[1].write(document.document_type.value)
        columns[2].write(f"{document.chunk_count} chunks")
        columns[3].write(document.uploaded_by)
        if columns[4].button("Delete", key=f"delete-{document.id}"):
            response = httpx.delete(
                f"{settings.api_base_url}/documents/{document.id}",
                headers=auth_headers(),
            )
            if response.status_code == 204:
                st.success(f"Deleted {document.filename}")
                st.rerun()
            else:
                st.error(f"Delete failed: {response.text}")


def render_admin_dashboard() -> None:
    st.title("Admin Dashboard")

    stats_response = httpx.get(f"{settings.api_base_url}/admin/stats", headers=auth_headers())
    if stats_response.status_code != 200:
        st.error("Could not load admin stats.")
        return
    stats = schemas.AdminStats.model_validate(stats_response.json())

    cols = st.columns(4)
    cols[0].metric("Documents", stats.document_count)
    cols[1].metric("Chunks", stats.chunk_count)
    cols[2].metric("Users", stats.user_count)
    cols[3].metric("Chat sessions", stats.chat_session_count)

    st.divider()
    if stats.last_evaluation is not None:
        render_evaluation_summary(stats.last_evaluation)
    else:
        st.caption("No evaluation report found yet.")

    st.divider()
    documents_response = httpx.get(f"{settings.api_base_url}/documents", headers=auth_headers())
    if documents_response.status_code != 200:
        st.error("Could not load documents.")
        return
    documents = [schemas.DocumentOut.model_validate(item) for item in documents_response.json()]
    render_documents(documents)


if st.session_state.get("role") != "admin":
    st.title("Admin Dashboard")
    st.write("Admin access required.")
else:
    render_admin_dashboard()
