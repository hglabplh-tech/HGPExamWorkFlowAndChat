# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Setuptools compatibility entry point for HGPExamWorkFlowAndChat."""

from pathlib import Path

from setuptools import find_packages, setup


ROOT = Path(__file__).parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


setup(
    name="hgp-exam-work-flow-and-chat",
    version="0.1.0",
    description="Course chat, curated knowledge, hybrid search, and assisted grading",
    long_description=README,
    long_description_content_type="text/markdown",
    author="Harald Glab-Plhak",
    license="MIT",
    python_requires=">=3.11",
    packages=find_packages(include=["backend*", "ml*"]),
    include_package_data=True,
    install_requires=[
        "fastapi>=0.115,<1",
        "uvicorn[standard]>=0.30,<1",
        "sqlalchemy[asyncio]>=2.0,<3",
        "asyncpg>=0.29,<1",
        "alembic>=1.13,<2",
        "pydantic-settings>=2.5,<3",
        "python-multipart>=0.0.9,<1",
        "pyjwt[crypto]>=2.9,<3",
        "argon2-cffi>=23.1,<26",
        "cryptography>=43,<46",
        "defusedxml>=0.7,<1",
        "httpx>=0.27,<1",
        "chromadb>=0.5,<2",
        "sentence-transformers>=3,<6",
        "reportlab>=4,<5",
        "pypdf>=5,<7",
    ],
    extras_require={
        "ml": [
            "torch>=2.3,<3",
            "transformers>=4.44,<5",
            "datasets>=2.21,<4",
            "torch-xla>=2.3,<3; platform_system == 'Linux'",
        ],
        "dev": [
            "pytest>=8,<9",
            "pytest-asyncio>=0.24,<1",
            "pytest-cov>=5,<7",
            "pytest-json-report>=1.5,<2",
            "pytest-benchmark>=5,<6",
            "ruff>=0.6,<1",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
