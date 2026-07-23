"""RPC-over-HTTP boundary contract tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from pathlib import Path

from backend.app.api_routes import auth, chat, content, courses, examinations, grading, playground, research, submissions, system, trust, users


def test_journey_endpoints_are_registered() -> None:
    """Ensure the aggregate router exposes the principal application journeys."""
    domain_routers = (auth, chat, content, courses, examinations, grading, playground, research, submissions, system, trust, users)
    paths = {route.path for module in domain_routers for route in module.router.routes}
    assert {
        "/api/v1/courses", "/api/v1/search", "/api/v1/research/questions",
        "/api/v1/conversations", "/api/v1/submissions", "/api/v1/trust-lists",
        "/api/v1/thesauri", "/api/v1/thesauri/upload",
        "/api/v1/knowledge/vocab.txt", "/api/v1/knowledge/vocabulary.json",
        "/api/v1/knowledge/rebuild-chroma",
        "/api/v1/courses/{course_id}/knowledge-base",
        "/api/v1/courses/{course_id}/knowledge-base/{name}",
        "/api/v1/users/me/totp/setup", "/api/v1/users/me/totp/verify",
        "/api/v1/auth/token", "/api/v1/auth/logout",
        "/api/v1/auth/check_totp", "/api/v1/auth/get_fresh_totp",
        "/api/v1/auth/send_totp",
        "/api/v1/auth/register/start",
        "/api/v1/auth/register/verify",
        "/api/v1/auth/register/activate",
        "/api/v1/courses/{course_id}/examinations/from-json",
        "/api/v1/courses/{course_id}/examinations/import.json",
        "/api/v1/examinations/{examination_id}/export.json",
        "/api/v1/examinations/{examination_id}/questions/{question_id}/score-draft",
        "/api/v1/conversations/{conversation_id}/messages/upload",
        "/api/v1/research/histories",
        "/api/v1/research/histories/{history_id}/activate",
        "/api/v1/research/histories/{history_id}",
        "/api/v1/research/histories/{history_id}/entries",
        "/api/v1/admin/mail-settings",
        "/api/v1/admin/logging-settings",
        "/api/v1/admin/configuration-cache",
        "/api/v1/admin/configuration-cache/invalidate",
        "/api/v1/playground/course",
        "/api/v1/playground/asag-score",
        "/api/v1/playground/asag-metrics",
    } <= paths


def test_route_modules_remain_small_enough_for_review() -> None:
    """Prevent domain route modules from regressing into a monolithic API file."""
    route_dir = Path(__file__).parents[1] / "backend" / "app" / "api_routes"
    assert max(len(path.read_text(encoding="utf-8").splitlines()) for path in route_dir.glob("*.py")) < 400
