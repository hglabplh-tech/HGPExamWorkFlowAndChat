"""Aggregate REST router for HGPExamWorkFlowAndChat.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""
from fastapi import APIRouter

from .api_routes.auth import router as auth_router
from .api_routes.chat import router as chat_router
from .api_routes.content import router as content_router
from .api_routes.courses import router as courses_router
from .api_routes.examinations import router as examinations_router
from .api_routes.grading import router as grading_router
from .api_routes.playground import router as playground_router
from .api_routes.research import router as research_router
from .api_routes.submissions import router as submissions_router
from .api_routes.system import router as system_router
from .api_routes.trust import router as trust_router
from .api_routes.users import router as users_router

router = APIRouter()
for child in (auth_router, users_router, trust_router, courses_router, examinations_router, content_router, research_router, submissions_router, chat_router, grading_router, playground_router, system_router):
    router.include_router(child)
