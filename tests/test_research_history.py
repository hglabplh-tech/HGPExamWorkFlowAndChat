"""Research-history query refinement tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
from types import SimpleNamespace

from backend.app.services.research_history import refine_query_with_history


def test_refine_query_uses_recent_history_terms_without_repeating_query() -> None:
    """Recent ASAG/search history contributes useful terms to the next query."""
    entries = [
        SimpleNamespace(label="M3 microprocessor", input_text="cache pipeline risc", output_summary="Apple silicon branch prediction"),
        SimpleNamespace(label="German history", input_text="Bundestag Basic Law", output_summary=""),
    ]
    refined = refine_query_with_history("pipeline", entries)
    assert refined.startswith("pipeline ")
    assert "microprocessor" in refined
    assert refined.count("pipeline") == 1
