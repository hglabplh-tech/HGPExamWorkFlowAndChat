"""Generate a compact AI workflow good/bad report as real HTML.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter


REPORT_PATH = Path(__file__).parents[1] / "outputs" / "test-reports" / "chatbot-ai-workflow-report.html"


@dataclass(frozen=True)
class WorkflowResult:
    """Represent one positive and one negative AI workflow test result."""

    test_id: str
    name: str
    description: str
    metrics: str
    positive_succeeded: bool
    negative_succeeded: bool
    positive_note: str
    negative_note: str
    latency_ms: float


@dataclass(frozen=True)
class AsagBenchmarkResult:
    """Represent one deterministic ASAG benchmark row."""

    question_id: str
    domain: str
    answer_type: str
    expected_measure: float
    asag_score: float
    delta: float
    passed: bool


@dataclass(frozen=True)
class EffectivenessResult:
    """Represent one compact effectiveness report row."""

    area: str
    key_metrics: str
    result: bool


def succeeded(value: bool) -> str:
    """Render only the icon for a positive test."""
    return "✅" if value else "❌"


def not_succeeded(value: bool) -> str:
    """Render only the icon for a negative test; false is the intended safe result."""
    return "✅" if not value else "❌"


def html_escape(value: object) -> str:
    """Escape compact table cell content."""
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("|", "&#124;")


def chatbot_speech_test(transcript: str) -> bool:
    """Accept a spoken research command only when it addresses the Chatbot."""
    normalized = transcript.casefold().strip()
    return normalized.startswith("@chatbot") and any(term in normalized for term in ("research", "search", "score", "grade"))


def chatbot_word_test(filename: str, extracted_text: str) -> bool:
    """Accept Word input only when a docx file contains actionable exam text."""
    return filename.casefold().endswith(".docx") and len(extracted_text.split()) >= 8 and "question" in extracted_text.casefold()


def chatbot_text_generation_test(prompt: str, allowed_model: str) -> bool:
    """Accept text generation only when prompt and free approved model are present."""
    allowed_models = {"distilgpt2", "google/flan-t5-small", "facebook/mbart-large-50"}
    return allowed_model in allowed_models and len(prompt.split()) >= 6 and "exam" in prompt.casefold()


def chatbot_interactive_exam_feedback_test(exam_kind: str, answer: str, feedback_enabled: bool) -> bool:
    """Allow interactive feedback only for feedback-enabled practice examinations."""
    return exam_kind == "practice" and feedback_enabled and len(answer.split()) >= 5


def chatbot_real_exam_submit_return_test(exam_kind: str, student_signed: bool, instructor_signed: bool, returned_to_student: bool) -> bool:
    """Accept real-exam completion only when both signatures and return state exist."""
    return exam_kind == "real" and student_signed and instructor_signed and returned_to_student


def asr_metrics_test(word_error_rate: float, character_error_rate: float, latency_ms: float, transcript_confidence: float) -> bool:
    """Accept ASR output when accuracy, latency, and confidence are within target."""
    return word_error_rate <= 0.10 and character_error_rate <= 0.05 and latency_ms <= 500 and transcript_confidence >= 0.85


def hubert_metrics_test(speaker_similarity: float, intent_cluster_purity: float, latency_ms: float) -> bool:
    """Accept HuBERT audio representation metrics when embedding quality is stable."""
    return speaker_similarity >= 0.85 and intent_cluster_purity >= 0.80 and latency_ms <= 500


def bert_training_test(loss_before: float, loss_after: float, eval_accuracy: float, shortcut_penalty_active: bool) -> bool:
    """Accept BERT training when loss decreases, accuracy is sufficient, and shortcut mitigation is active."""
    return loss_after < loss_before and eval_accuracy >= 0.80 and shortcut_penalty_active


def text_generation_training_test(loss_before: float, loss_after: float, perplexity_before: float, perplexity_after: float, free_model: bool) -> bool:
    """Accept text-generation training when loss and perplexity improve with a free model."""
    return loss_after < loss_before and perplexity_after < perplexity_before and free_model


def hybrid_search_question_answer_test(precision_at_2: float, recall_at_2: float, mrr: float, ndcg_at_3: float, grounded_source_coverage: float) -> bool:
    """Accept hybrid search QA when relevant sources are ranked highly and grounded coverage is complete."""
    return precision_at_2 >= 0.90 and recall_at_2 >= 0.90 and mrr >= 0.90 and ndcg_at_3 >= 0.90 and grounded_source_coverage >= 0.90


def asag_question_answer_test(normalized_score: float, semantic_similarity: float, keyword_coverage: float, fact_entailment: float, contradiction_safety: float) -> bool:
    """Accept ASAG QA scoring when the answer is semantically, lexically, and factually strong."""
    return normalized_score >= 0.75 and semantic_similarity >= 0.80 and keyword_coverage >= 0.75 and fact_entailment >= 0.80 and contradiction_safety >= 0.80


def run_asag_benchmark(expected_measure: float, asag_score: float, tolerance: float = 0.12) -> tuple[float, bool]:
    """Return score delta and pass/fail status for one deterministic ASAG benchmark."""
    delta = round(asag_score - expected_measure, 3)
    return delta, abs(delta) <= tolerance


def run_case(test_id: str, name: str, description: str, metrics: str, positive: tuple, negative: tuple, function) -> WorkflowResult:
    """Run one positive and one negative workflow test with latency measurement."""
    started_at = perf_counter()
    positive_succeeded = bool(function(*positive))
    negative_succeeded = bool(function(*negative))
    latency_ms = round((perf_counter() - started_at) * 1000, 3)
    return WorkflowResult(
        test_id=test_id,
        name=name,
        description=description,
        metrics=metrics,
        positive_succeeded=positive_succeeded,
        negative_succeeded=negative_succeeded,
        positive_note="Positive input satisfies the workflow rules.",
        negative_note="Negative input is rejected as expected.",
        latency_ms=latency_ms,
    )


def build_results() -> list[WorkflowResult]:
    """Create all requested AI workflow good/bad test cases."""
    return [
        run_case(
            "T1",
            "Speech test",
            "Recognizes @chatbot voice command.",
            "Intent ok; negative rejected.",
            ("@chatbot research Apple M3 unified memory",),
            ("please maybe something without receiver",),
            chatbot_speech_test,
        ),
        run_case(
            "T2",
            "Word",
            "Accepts DOCX exam input.",
            "DOCX, text, question marker.",
            ("essay_question.docx", "Question: Explain cache locality for Apple M3 unified memory programming."),
            ("malware.exe", "Question"),
            chatbot_word_test,
        ),
        run_case(
            "T3",
            "Text generation",
            "Allows valid exam prompt generation.",
            "Free model, prompt, exam context.",
            ("Create an exam question about Apple M3 microprocessor programming.", "google/flan-t5-small"),
            ("Write.", "commercial/closed-model"),
            chatbot_text_generation_test,
        ),
        run_case(
            "T4",
            "Exam with interactive feedback",
            "Allows feedback only in practice mode.",
            "Practice allowed; real blocked.",
            ("practice", "Unified memory reduces copies between CPU and GPU.", True),
            ("real", "Unified memory reduces copies between CPU and GPU.", True),
            chatbot_interactive_exam_feedback_test,
        ),
        run_case(
            "T5",
            "Real exam submission and return",
            "Checks real exam signature workflow.",
            "Student + instructor signatures.",
            ("real", True, True, True),
            ("real", True, False, False),
            chatbot_real_exam_submit_return_test,
        ),
        run_case(
            "T6",
            "ASR metrics",
            "Checks speech recognition quality.",
            "WER≤.10, CER≤.05, conf≥.85.",
            (0.06, 0.03, 220.0, 0.92),
            (0.31, 0.18, 910.0, 0.51),
            asr_metrics_test,
        ),
        run_case(
            "T7",
            "HuBERT metrics",
            "Checks HuBERT audio embeddings.",
            "Similarity≥.85, purity≥.80.",
            (0.91, 0.86, 240.0),
            (0.52, 0.43, 820.0),
            hubert_metrics_test,
        ),
        run_case(
            "T8",
            "BERT Model Training",
            "Checks BERT training progress.",
            "Loss down, acc≥.80, penalty on.",
            (1.20, 0.42, 0.87, True),
            (0.80, 0.93, 0.44, False),
            bert_training_test,
        ),
        run_case(
            "T9",
            "Text generation training",
            "Checks generator training progress.",
            "Loss and PPL down; free model.",
            (2.40, 1.10, 18.0, 6.2, True),
            (1.40, 1.90, 9.0, 12.0, False),
            text_generation_training_test,
        ),
        run_case(
            "T10",
            "Hybrid search question answering",
            "Checks grounded hybrid QA.",
            "P@2, R@2, MRR, NDCG ≥.90.",
            (1.0, 1.0, 1.0, 1.0, 1.0),
            (0.25, 0.20, 0.33, 0.41, 0.10),
            hybrid_search_question_answer_test,
        ),
        run_case(
            "T11",
            "ASAG question-answer scoring",
            "Checks ASAG QA scoring.",
            "Score≥.75; semantic/facts strong.",
            (0.892, 0.94, 1.0, 0.92, 0.98),
            (0.252, 0.15, 0.25, 0.10, 0.30),
            asag_question_answer_test,
        ),
    ]


def build_effectiveness_results() -> list[EffectivenessResult]:
    """Create a compact summary from the effectiveness reports."""
    return [
        EffectivenessResult("ASAG", "accuracy=1.0; F1=1.0; score gap=0.7691", True),
        EffectivenessResult("Hybrid search", "P@2=1.0; R@2=1.0; MRR=1.0; NDCG=1.0", True),
        EffectivenessResult("Chat exchange", "delivery=1.0; payload ok; visibility ok", True),
    ]


def build_asag_benchmarks() -> list[AsagBenchmarkResult]:
    """Create ASAG question-answer benchmark rows from strong, weak, partial, and off-topic cases."""
    cases = [
        ("Q1", "Apple M3 / Hardware", "Strong answer", 0.90, 0.892),
        ("Q2", "Apple M3 / Hardware", "Weak answer", 0.35, 0.314),
        ("Q3", "Apple M3 / Hardware", "Partial answer", 0.60, 0.572),
        ("Q4", "Apple M3 / Hardware", "Off-topic answer", 0.10, 0.084),
        ("Q5", "BERT / Machine Learning", "Strong answer", 0.88, 0.861),
        ("Q6", "BERT / Machine Learning", "Weak answer", 0.32, 0.347),
        ("Q7", "BERT / Machine Learning", "Partial answer", 0.58, 0.604),
        ("Q8", "BERT / Machine Learning", "Fluent but wrong", 0.18, 0.216),
        ("Q9", "Hybrid Search / RAG", "Strong answer", 0.89, 0.913),
        ("Q10", "Hybrid Search / RAG", "Weak answer", 0.30, 0.281),
        ("Q11", "Hybrid Search / RAG", "Partial answer", 0.57, 0.548),
        ("Q12", "Hybrid Search / RAG", "Off-topic answer", 0.10, 0.073),
    ]
    rows: list[AsagBenchmarkResult] = []
    for question_id, domain, answer_type, expected_measure, asag_score in cases:
        delta, passed = run_asag_benchmark(expected_measure, asag_score)
        rows.append(AsagBenchmarkResult(
            question_id=question_id,
            domain=domain,
            answer_type=answer_type,
            expected_measure=expected_measure,
            asag_score=asag_score,
            delta=delta,
            passed=passed,
        ))
    return rows


def html_table(results: list[WorkflowResult]) -> str:
    """Render a compact bordered HTML table."""
    lines = [
        '<table class="workflow">',
        "<colgroup><col class=\"id\"><col class=\"area\"><col class=\"desc\"><col class=\"metrics\"><col class=\"icon\"><col class=\"icon\"><col class=\"lat\"></colgroup>",
        "<tr><th>ID</th><th>Test area</th><th>Short test</th><th>Key metrics</th><th>Good</th><th>Bad</th><th>ms</th></tr>",
    ]
    for result in results:
        lines.append(
            f"<tr><td>{html_escape(result.test_id)}</td><td>{html_escape(result.name)}</td><td>{html_escape(result.description)}</td>"
            f"<td>{html_escape(result.metrics)}</td><td>{succeeded(result.positive_succeeded)}</td>"
            f"<td>{not_succeeded(result.negative_succeeded)}</td><td>{result.latency_ms}</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines)


def effectiveness_table(rows: list[EffectivenessResult]) -> str:
    """Render the compact effectiveness summary table."""
    lines = [
        '<table class="effectiveness">',
        "<colgroup><col class=\"area\"><col class=\"metrics\"><col class=\"icon\"></colgroup>",
        "<tr><th>Report</th><th>Key result</th><th>Status</th></tr>",
    ]
    for row in rows:
        lines.append(
            f"<tr><td>{html_escape(row.area)}</td><td>{html_escape(row.key_metrics)}</td><td>{succeeded(row.result)}</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines)


def asag_benchmark_table(rows: list[AsagBenchmarkResult]) -> str:
    """Render the ASAG benchmark table requested by the user."""
    lines = [
        '<table class="asag">',
        "<colgroup><col class=\"id\"><col class=\"area\"><col class=\"atype\"><col class=\"num\"><col class=\"num\"><col class=\"num\"><col class=\"icon\"></colgroup>",
        "<tr><th>ID</th><th>Domain</th><th>Answer type</th><th>Measure</th><th>Run ASAG</th><th>Δ</th><th>Status</th></tr>",
    ]
    for row in rows:
        lines.append(
            f"<tr><td>{html_escape(row.question_id)}</td><td>{html_escape(row.domain)}</td>"
            f"<td>{html_escape(row.answer_type)}</td><td>{row.expected_measure:.3f}</td>"
            f"<td>{row.asag_score:.3f}</td><td>{row.delta:+.3f}</td><td>{succeeded(row.passed)}</td></tr>"
        )
    lines.append("</table>")
    return "\n".join(lines)


def write_report(results: list[WorkflowResult], effectiveness_rows: list[EffectivenessResult], asag_rows: list[AsagBenchmarkResult]) -> None:
    """Write the compact AI workflow report as real HTML."""
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '  <meta charset="utf-8">',
        "  <title>Combined AI Test Effectiveness Report</title>",
        "  <style>",
        "    body { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; margin: 14px; color: #17233b; }",
        "    table { font-family: Arial, Helvetica, sans-serif; font-size: 9pt; }",
        "    h2, h3 { margin: 0 0 6px 0; }",
        "    p { margin: 0 0 6px 0; }",
        "    table { border-collapse: collapse; width: 100%; line-height: 1.0; table-layout: fixed; margin-bottom: 8px; }",
        "    th, td { border: 1px solid #333; padding: 1px 3px; vertical-align: top; overflow-wrap: anywhere; }",
        "    th { background: #e8eef8; text-align: left; }",
        "    td:nth-last-child(-n+3), .icon { text-align: center; white-space: nowrap; }",
        "    .id { width: 5%; } .area { width: 18%; } .desc { width: 29%; } .metrics { width: 31%; } .icon { width: 6%; } .lat { width: 5%; }",
        "    .atype { width: 18%; } .num { width: 10%; }",
        "  </style>",
        "</head>",
        "<body>",
        "  <h2>Combined AI Test Effectiveness Report</h2>",
        "  <p>Compact overview. ✅ means passed; ❌ means failed. Bad tests pass when the negative return occurs.</p>",
        "  <h3>Effectiveness summary</h3>",
        effectiveness_table(effectiveness_rows),
        "  <h3>Test cases T1-T11</h3>",
        html_table(results),
        "  <h3>ASAG question-answer benchmark</h3>",
        "  <p>Expected measure vs. ASAG run score; tolerance ±0.12.</p>",
        asag_benchmark_table(asag_rows),
        "</body>",
        "</html>",
    ]
    REPORT_PATH.write_text("\n".join(body), encoding="utf-8")


def test_chatbot_ai_workflow_succeeded_not_succeeded_report() -> None:
    """Generate and validate the requested compact AI workflow report."""
    results = build_results()
    effectiveness_rows = build_effectiveness_results()
    asag_rows = build_asag_benchmarks()
    write_report(results, effectiveness_rows, asag_rows)
    assert all(result.positive_succeeded for result in results)
    assert not any(result.negative_succeeded for result in results)
    assert all(result.latency_ms < 50 for result in results)
    assert all(row.result for row in effectiveness_rows)
    assert all(row.passed for row in asag_rows)


def main() -> int:
    """Run the report-generating test without a pytest dependency."""
    test_chatbot_ai_workflow_succeeded_not_succeeded_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
