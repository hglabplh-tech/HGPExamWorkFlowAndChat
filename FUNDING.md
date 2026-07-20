<!-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. -->

# Fund HGPExamWorkFlowAndChat

HGPExamWorkFlowAndChat is an open-source Python platform for secure learning,
course collaboration, examination preparation, hybrid search, and assisted
grading. The project combines a FastAPI backend, PostgreSQL, ChromaDB, HTML5
interfaces, native-client wrappers, ASAG scoring, research history, signed exam
submission evidence, and AI-assisted knowledge retrieval.

The goal is to make advanced examination workflows available to schools,
universities, small institutions, and independent educators without forcing them
onto expensive proprietary systems. Funding helps turn the current alpha
prototype into a reliable, documented, testable, and deployable service that can
be reviewed by teachers, administrators, developers, and security auditors.

## Why this project matters

Modern education needs tools that let students prepare collaboratively while
still protecting examination integrity. HGPExamWorkFlowAndChat is designed around
that balance:

- Students can research course material, ask AI-assisted questions, use chat
  rooms, share results with selected groups, and prepare with realistic test
  examinations.
- Instructors can create exams, release practice or real examinations, review
  AI-supported grading, override scores, and return signed grading reports.
- Institutions keep PostgreSQL as the canonical source of record, while ChromaDB
  acts as a rebuildable semantic index.
- Security features include bearer sessions, request nonces, TOTP flows,
  certificate-aware requests, signed examination evidence, audit records, and
  retention-oriented database design.
- Search and scoring are configurable, combining full-text search, BM25,
  thesaurus expansion, sentence-transformer semantics, ASAG metrics, fact
  checks, and discipline-specific weights.

## What funding supports

Funding through Stripe helps pay for:

- Hardening the Docker and cloud deployment path.
- Expanding tests for RPC-over-HTTP APIs, workflows, security services, scoring, and
  import/export functions.
- Improving documentation for administrators, instructors, and developers.
- Building safer model-training and evaluation workflows for CPU-first
  deployments.
- Improving accessibility and responsive behavior in the HTML5 UI.
- Auditing exam submission, evidence, and retention workflows.
- Reducing operational complexity for small institutions.

## Funding link

Sponsor and project support is configured through GitHub’s funding integration:

<https://stripe.com>

Thank you for helping move this project from an ambitious prototype toward a
usable open education platform.
