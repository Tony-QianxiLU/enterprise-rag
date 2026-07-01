import json
from pathlib import Path

from enterprise_rag.evaluation.evaluate import evaluate


def test_evaluate_generates_reports_with_perfect_pass_rate(tmp_path: Path) -> None:
    summary = evaluate(
        cases_path=Path("data/evaluation_cases.jsonl"),
        json_output_path=Path("reports/evaluation-report.json"),
        markdown_output_path=Path("reports/evaluation-report.md"),
        eval_chroma_dir=tmp_path / "eval_chroma",
        eval_db_path=tmp_path / "eval.db",
    )

    assert summary.total_cases == 5
    assert summary.overall_pass_rate == 1.0
    assert summary.retrieval_accuracy == 1.0
    assert summary.citation_coverage == 1.0
    assert summary.groundedness_rate == 1.0

    json_report_path = Path("reports/evaluation-report.json")
    markdown_report_path = Path("reports/evaluation-report.md")
    assert json_report_path.exists()
    assert markdown_report_path.exists()

    report_payload = json.loads(json_report_path.read_text(encoding="utf-8"))
    assert report_payload["overall_pass_rate"] == 1.0
    assert len(report_payload["results"]) == 5

    markdown_text = markdown_report_path.read_text(encoding="utf-8")
    assert "# RAG Evaluation Report" in markdown_text
