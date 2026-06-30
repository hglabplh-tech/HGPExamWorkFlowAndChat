<!-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. -->

# Student and instructor workflows

## Visibility

Research interactions have one of three scopes:

- `private`: only the owner and authorized instructors/administrators.
- `conversation`: only explicit members of the selected direct/group chat.
- `course`: all enrolled course members; eligible to improve later retrieval.

Training additionally requires `training_opt_in=true`. Public student research is
curated into a pending dataset and must be approved by staff. Teacher-returned
grading examples are eligible automatically because the teacher score is the
supervisory label. Visibility changes, approvals, shares, grades, and releases
are audited.

## Student journey

1. Enroll in a course and access staff-approved books/materials.
2. Ask `/research/questions`; the answer combines weighted PostgreSQL full-text,
   Chroma/Sentence Transformer retrieval, and deliberately course-public history.
3. Keep the interaction private, share it with one conversation, or publish it
   to the course with optional training consent.
4. Create/join a direct or group conversation and exchange persisted messages,
   research results, and scored practice attempts.
5. Open released practice examinations and submit signed answers.
6. The immutable exam hash, student certificate, and student signature are
   stored together. Receive an AI-only PDF report with provisional ASAG metrics
   and feedback. The practice score
   may be shared only by its owner and only with explicit conversation members.
7. Open a released real examination and submit signed answers. No AI or teacher
   feedback is returned at submission time.
8. After instructor grading, the instructor signs the original evidence hash
   plus final grading hash. On explicit return, retrieve the corrected work,
   final mark, dual-signature evidence, and PDF report.

## Instructor journey

1. Use the same research and chat services, subject to course membership.
2. Create a draft examination manually or request an AI-generated, editable
   draft from objectives. AI output never releases itself.
3. Add reviewed questions, reference answers, concepts, facts, and marks.
4. Release a practice or real examination with an optional closing time.
5. Review submitted work. The same weighted ASAG engine proposes grades for real
   exams, but students cannot see those proposals.
6. Correct or override the proposal, recording scores, feedback, identity, and
   reason in the audit trail.
7. Sign the final grading package with an active application-trusted instructor
   certificate and explicitly return it; only then does real-exam feedback and
   its report become visible to the student.

## Nightly training

The Kubernetes CronJob runs `python -m backend.training_job` at 02:00. It:

1. creates pending retrieval examples from course-public, opted-in research;
2. creates approved scoring examples from teacher-returned question scores;
3. uses only approved examples and enforces a configurable minimum sample size;
4. fine-tunes a Sentence Transformer retrieval model and a CrossEncoder scoring
   model when `NIGHTLY_TRAINING_MODE=train`;
5. records every run and atomically publishes successful artifacts through a
   `current` model link on shared model storage.

Production promotion should add held-out evaluation thresholds and rollback
approval before allowing newly trained models to affect formal grading.
