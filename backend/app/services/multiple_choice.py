"""Deterministic single- and multiple-choice scoring.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""


def score_choice_answer(
    submitted: str | list[str],
    correct_options: list[str],
    maximum: float,
    partial_credit: bool = False,
) -> dict:
    """Score exact choices or bounded partial credit with wrong-option penalties."""
    selected = {submitted} if isinstance(submitted, str) else set(submitted)
    correct = set(correct_options)
    if not correct:
        raise ValueError("Choice question has no configured correct option")
    if selected == correct:
        ratio = 1.0
    elif partial_credit:
        ratio = max(0.0, (len(selected & correct) - len(selected - correct)) / len(correct))
    else:
        ratio = 0.0
    return {
        "score": round(maximum * ratio, 3),
        "max_score": maximum,
        "normalized_score": round(ratio, 6),
        "selected_count": len(selected),
        "correct_count": len(correct),
        "exact_match": selected == correct,
        "requires_teacher_review": False,
        "warnings": [],
        "signals": {"choice_accuracy": round(ratio, 6)},
    }
