"""Deterministic, balanced random work-group assignment.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import random
import uuid


def assign_random_groups(student_ids: list[uuid.UUID], maximum_size: int, seed: str) -> list[list[uuid.UUID]]:
    """Shuffle reproducibly and distribute students without singleton tail groups."""
    if maximum_size < 2 or len(student_ids) < 2:
        raise ValueError("At least two students and a group size of two are required")
    shuffled = list(student_ids)
    random.Random(seed).shuffle(shuffled)
    group_count = max(1, (len(shuffled) + maximum_size - 1) // maximum_size)
    return [shuffled[index::group_count] for index in range(group_count)]
