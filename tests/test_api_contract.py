"""REST-boundary contract tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from pathlib import Path

from backend.app.api_routes import chat, content, courses, examinations, grading, research, submissions, trust, users


def test_journey_endpoints_are_registered() -> None:
    """Ensure the aggregate router exposes the principal application journeys."""
    domain_routers = (chat, content, courses, examinations, grading, research, submissions, trust, users)
    paths = {route.path for module in domain_routers for route in module.router.routes}
    assert {
        "/api/v1/courses", "/api/v1/search", "/api/v1/research/questions",
        "/api/v1/conversations", "/api/v1/submissions", "/api/v1/trust-lists",
        "/api/v1/thesauri", "/api/v1/thesauri/upload",
        "/api/v1/knowledge/vocab.txt", "/api/v1/knowledge/vocabulary.json",
        "/api/v1/users/me/totp/setup", "/api/v1/users/me/totp/verify",
        "/api/v1/courses/{course_id}/examinations/from-json",
        "/api/v1/courses/{course_id}/examinations/import.json",
        "/api/v1/examinations/{examination_id}/export.json",
    } <= paths


def test_route_modules_remain_small_enough_for_review() -> None:
    """Prevent domain route modules from regressing into a monolithic API file."""
    route_dir = Path(__file__).parents[1] / "backend" / "app" / "api_routes"
    assert max(len(path.read_text(encoding="utf-8").splitlines()) for path in route_dir.glob("*.py")) < 400
