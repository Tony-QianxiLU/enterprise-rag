# Evaluation

This project includes an offline RAG evaluation suite that runs without paid API calls.

The goal is to make the project interview-ready by showing not only that the app works, but also that retrieval and answer behavior can be measured after code, prompt, or model changes.

## What It Measures

| Metric | Meaning |
| --- | --- |
| Retrieval accuracy | Whether the expected source document appears among the retrieved citations. |
| Citation coverage | Whether the answer includes at least one citation. |
| Groundedness rate | Whether the generated answer includes the expected terms drawn from the retrieved context. |
| Overall pass rate | Whether a case passes retrieval, citation, and groundedness checks together. |
| Average latency | How long each benchmark question takes to run locally, end to end (retrieval + generation). |

## Benchmark Dataset

The benchmark lives in:

```text
data/evaluation_cases.jsonl
```

Each JSONL row includes:

- `id`
- `question`
- `expected_source`
- `expected_terms`

The current dataset covers a fixture corpus of five synthetic enterprise documents (employee onboarding, security policy, product FAQ, incident response runbook, vendor contract summary), with one benchmark question per document:

- Employee benefits enrollment window
- Security password rotation policy
- Product refund policy
- Incident response severity escalation
- Vendor contract termination notice

The evaluation harness (`evaluation/evaluate.py`) ingests this fixture corpus into an isolated Chroma directory and SQLite database (never the app's real `data/chroma` or `data/enterprise_rag.db`), forcing the deterministic `HashEmbeddingProvider` and `TemplateLLMProvider` regardless of whether `OPENAI_API_KEY` is configured, so results are reproducible in CI.

## Run Evaluation

```bash
PYTHONPATH=src uv run rag-evaluate
```

Generated reports:

```text
reports/evaluation-report.md
reports/evaluation-report.json
```

## Current Result

| Metric | Result |
| --- | ---: |
| Retrieval accuracy | 100% |
| Citation coverage | 100% |
| Groundedness rate | 100% |
| Overall pass rate | 100% |
| Average latency | 5.6 ms |

Total cases: 5. All 5 pass retrieval, citation, and groundedness checks.

See [reports/evaluation-report.md](../reports/evaluation-report.md) for case-level details, including per-case latency and which sources were retrieved.

## CI Integration

GitHub Actions runs the evaluation suite after linting and tests:

```bash
PYTHONPATH=src uv run rag-evaluate
```

This means changes to chunking, retrieval, generation, or evaluation logic are checked automatically on push and pull request.

## Future Improvements

- Add harder negative cases where the correct answer should say the context is insufficient.
- Add retrieval precision and recall at top-k, not just pass/fail source matching.
- Track latency and metric trends over time instead of only the latest run.
- Add optional LLM-as-judge evaluation for answer helpfulness, not just term-matching groundedness.
- Store generated reports as CI artifacts.
- Expand the fixture corpus and add multi-document conflict cases.
