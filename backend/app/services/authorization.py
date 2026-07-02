"""Role and explicit-permission authorization utilities.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from ..models import Role, User


KNOWN_PERMISSIONS = {
    "users.manage", "courses.instruct", "content.manage", "grading.manage",
    "training.manage", "trust.manage", "reports.read_all", "email.send",
}

ROLE_PERMISSIONS = {
    Role.student: set(),
    Role.teacher: {"courses.instruct", "grading.manage", "email.send"},
    Role.staff: {"courses.instruct", "content.manage", "grading.manage", "training.manage", "reports.read_all", "email.send"},
    Role.admin: KNOWN_PERMISSIONS,
}


def validate_permissions(values: list[str]) -> list[str]:
    """Normalize known permissions and reject misspelled security controls."""
    unknown = set(values) - KNOWN_PERMISSIONS
    if unknown:
        raise ValueError(f"Unknown permissions: {', '.join(sorted(unknown))}")
    return sorted(set(values))


def has_permission(user: User, permission: str) -> bool:
    """Return whether role defaults or explicit grants provide a permission."""
    return permission in ROLE_PERMISSIONS.get(user.role, set()) or permission in set(user.permissions or [])
