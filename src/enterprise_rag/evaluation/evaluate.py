"""Offline RAG evaluation benchmark: deterministic, no paid API calls.

Forces HashEmbeddingProvider + TemplateLLMProvider so the benchmark is
reproducible in CI regardless of whether OPENAI_API_KEY is configured, and
writes its own isolated Chroma/sqlite state so it never touches the real
app's data/chroma or data/enterprise_rag.db.
"""

import time
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from enterprise_rag import schemas
from enterprise_rag.config import Settings
from enterprise_rag.db import Base
from enterprise_rag.providers.embeddings import HashEmbeddingProvider
from enterprise_rag.providers.llm import TemplateLLMProvider
from enterprise_rag.rag.pipeline import RagPipeline
from enterprise_rag.retrieval.retriever import Retriever
from enterprise_rag.retrieval.vector_store import ChromaVectorStore

FIXTURE_CORPUS: dict[str, str] = {
    "employee-onboarding.txt": (
        "Employee Onboarding Guide. New hires must complete identity verification "
        "and laptop setup during their first week. Employees may enroll in health "
        "benefits within 30 days of their start date through the benefits enrollment "
        "portal. Missing this window requires waiting for the next open enrollment "
        "period unless a qualifying life event occurs."
    ),
    "security-policy.txt": (
        "Information Security Policy. All employees must rotate account passwords "
        "every 90 days and enable multi-factor authentication on every corporate "
        "system. Shared credentials are prohibited, and suspected compromises must "
        "be reported to the security team within one hour of discovery."
    ),
    "product-faq.txt": (
        "Product FAQ. Customers are eligible for a refund within the 30-day refund "
        "window starting from the purchase date, provided the subscription has not "
        "been used beyond the trial limits. Refund requests should be sent to "
        "billing@acme.example with the original order number."
    ),
    "incident-response-runbook.txt": (
        "Incident Response Runbook. When an on-call engineer declares a Severity 1 "
        "incident, the on-call incident commander must be notified immediately and "
        "a war room bridge opened within fifteen minutes. Lower severity incidents "
        "follow the standard triage queue during business hours."
    ),
    "vendor-contract-summary.txt": (
        "Vendor Contract Summary. The master services agreement with Acme Cloud "
        "Services renews annually and requires 60 days written notice to terminate "
        "before the renewal date. Early termination outside that window triggers "
        "an early-exit fee equal to one quarter of the annual contract value."
    ),
}

_EVAL_CHUNK_SIZE_TOKENS = 400
_EVAL_CHUNK_OVERLAP_TOKENS = 0


def _build_eval_pipeline(persist_dir: Path, upload_dir: Path) -> RagPipeline:
    settings = Settings(
        openai_api_key=None,
        chroma_persist_dir=str(persist_dir),
        upload_dir=upload_dir,
        chunk_size_tokens=_EVAL_CHUNK_SIZE_TOKENS,
        chunk_overlap_tokens=_EVAL_CHUNK_OVERLAP_TOKENS,
    )
    embedding_provider = HashEmbeddingProvider()
    llm_provider = TemplateLLMProvider()
    vector_store = ChromaVectorStore(
        persist_dir=settings.chroma_persist_dir, embedding_provider=embedding_provider
    )
    retriever = Retriever(vector_store=vector_store, embedding_provider=embedding_provider)
    return RagPipeline(settings, embedding_provider, llm_provider, vector_store, retriever)


def load_evaluation_cases(path: Path) -> list[schemas.EvaluationCase]:
    cases: list[schemas.EvaluationCase] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if not stripped:
                continue
            cases.append(schemas.EvaluationCase.model_validate_json(stripped))
    return cases


def run_evaluation(
    pipeline: RagPipeline,
    db_session_factory: sessionmaker,
    cases: list[schemas.EvaluationCase],
    corpus: dict[str, str],
) -> schemas.EvaluationSummary:
    ingest_db = db_session_factory()
    try:
        for filename, text in corpus.items():
            pipeline.ingest_document(
                ingest_db,
                file_bytes=text.encode("utf-8"),
                filename=filename,
                uploaded_by="evaluation-harness",
            )
    finally:
        ingest_db.close()

    results: list[schemas.EvaluationResult] = []
    for case in cases:
        query_db = db_session_factory()
        try:
            started_at = time.perf_counter()
            response = pipeline.query(
                query_db,
                session_id=None,
                message=case.question,
                user_id="evaluation-harness",
            )
            latency_ms = (time.perf_counter() - started_at) * 1000
        finally:
            query_db.close()

        retrieved_sources = [citation.source for citation in response.citations]
        answer_lower = response.answer.lower()

        retrieval_passed = case.expected_source in retrieved_sources
        citation_passed = len(response.citations) >= 1
        groundedness_passed = all(
            term.lower() in answer_lower for term in case.expected_terms
        )

        results.append(
            schemas.EvaluationResult(
                case_id=case.id,
                question=case.question,
                answer=response.answer,
                citations=retrieved_sources,
                retrieval_passed=retrieval_passed,
                citation_passed=citation_passed,
                groundedness_passed=groundedness_passed,
                latency_ms=latency_ms,
            )
        )

    return summarize_results(results)


def summarize_results(results: list[schemas.EvaluationResult]) -> schemas.EvaluationSummary:
    total_cases = len(results)
    if total_cases == 0:
        return schemas.EvaluationSummary(
            total_cases=0,
            retrieval_accuracy=0.0,
            citation_coverage=0.0,
            groundedness_rate=0.0,
            overall_pass_rate=0.0,
            average_latency_ms=0.0,
            results=[],
        )

    passed_cases = sum(
        result.retrieval_passed and result.citation_passed and result.groundedness_passed
        for result in results
    )

    return schemas.EvaluationSummary(
        total_cases=total_cases,
        retrieval_accuracy=_rate(results, "retrieval_passed"),
        citation_coverage=_rate(results, "citation_passed"),
        groundedness_rate=_rate(results, "groundedness_passed"),
        overall_pass_rate=passed_cases / total_cases,
        average_latency_ms=sum(result.latency_ms for result in results) / total_cases,
        results=results,
    )


def _rate(results: list[schemas.EvaluationResult], field_name: str) -> float:
    if not results:
        return 0.0
    return sum(bool(getattr(result, field_name)) for result in results) / len(results)


def render_markdown_report(summary: schemas.EvaluationSummary) -> str:
    lines = [
        "# RAG Evaluation Report",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary.total_cases}",
        f"- Retrieval accuracy: {summary.retrieval_accuracy:.0%}",
        f"- Citation coverage: {summary.citation_coverage:.0%}",
        f"- Groundedness rate: {summary.groundedness_rate:.0%}",
        f"- Overall pass rate: {summary.overall_pass_rate:.0%}",
        f"- Average latency: {summary.average_latency_ms:.1f} ms",
        "",
        "## Case Results",
        "",
        "| Case | Retrieval | Citations | Grounded | Latency | Retrieved sources |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]

    for result in summary.results:
        lines.append(
            "| "
            f"{result.case_id} | "
            f"{_format_status(result.retrieval_passed)} | "
            f"{_format_status(result.citation_passed)} | "
            f"{_format_status(result.groundedness_passed)} | "
            f"{result.latency_ms:.1f} ms | "
            f"{', '.join(result.citations) or 'None'} |"
        )

    return "\n".join(lines) + "\n"


def write_json_report(summary: schemas.EvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")


def write_markdown_report(summary: schemas.EvaluationSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown_report(summary), encoding="utf-8")


def _format_status(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def evaluate(
    cases_path: Path = Path("data/evaluation_cases.jsonl"),
    json_output_path: Path = Path("reports/evaluation-report.json"),
    markdown_output_path: Path = Path("reports/evaluation-report.md"),
    eval_chroma_dir: Path = Path("data/eval_chroma"),
    eval_db_path: Path = Path("data/eval.db"),
) -> schemas.EvaluationSummary:
    if eval_db_path.exists():
        eval_db_path.unlink()

    engine = create_engine(
        f"sqlite:///{eval_db_path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    pipeline = _build_eval_pipeline(eval_chroma_dir, eval_chroma_dir.parent / "eval_uploads")
    cases = load_evaluation_cases(cases_path)
    summary = run_evaluation(pipeline, session_factory, cases, FIXTURE_CORPUS)

    write_json_report(summary, json_output_path)
    write_markdown_report(summary, markdown_output_path)

    return summary


def main() -> None:
    summary = evaluate()
    print(
        "Evaluation complete: "
        f"retrieval={summary.retrieval_accuracy:.0%}, "
        f"citations={summary.citation_coverage:.0%}, "
        f"groundedness={summary.groundedness_rate:.0%}, "
        f"overall_pass_rate={summary.overall_pass_rate:.0%}, "
        f"latency={summary.average_latency_ms:.1f}ms"
    )


if __name__ == "__main__":
    main()
