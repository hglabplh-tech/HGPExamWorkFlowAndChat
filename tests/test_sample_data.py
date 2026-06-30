"""Schema and quality tests for bundled sample data.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import csv
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_sample_courses_have_questions_and_scoring_evidence() -> None:
    """Every sample course supplies useful reference answers and facts."""
    files = sorted((ROOT / "data" / "sample_courses").glob("*.json"))
    assert len(files) == 2
    for file in files:
        course = json.loads(file.read_text(encoding="utf-8"))
        assert len(course["modules"]) >= 4
        assert len(course["sample_questions"]) >= 5
        assert all(question["keywords"] and question["facts"] for question in course["sample_questions"])


def test_training_scores_are_valid_and_include_label_contrast() -> None:
    """Synthetic sets contain valid scores and both strong and weak answers."""
    for file in (ROOT / "data" / "training").glob("*_asag.csv"):
        rows = list(csv.DictReader(file.open(encoding="utf-8", newline="")))
        scores = [float(row["normalized_score"]) for row in rows]
        assert len(rows) >= 8
        assert all(0 <= score <= 1 for score in scores)
        assert min(scores) <= 0.1 and max(scores) >= 0.9
