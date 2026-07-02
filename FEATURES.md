<!-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. -->

# HGPExamWorkFlowAndChat feature inventory

This document describes the implemented project features and their important
attributes as detected from the current source tree. The project is alpha
software and should still be reviewed, threat-modeled, configured, and
integration-tested before production use.

## 1. Platform architecture

**Purpose:** provide a modular Python/FastAPI learning, chat, search, exam, and
grading service.

**Attributes**

- Backend: FastAPI route modules under `backend/app/api_routes/`.
- Business services: `backend/app/services/`.
- Persistence: PostgreSQL ORM models under `backend/app/db_models/`.
- Frontend: responsive HTML5/PWA client in `frontend/`.
- Native packaging: Capacitor/Tauri wrapper in `clients/native/`.
- ML experiments: standalone scripts in `ml/`.
- Infrastructure: Caddy TLS proxy, PostgreSQL setup, migrations, OCSP config.
- Canonical data store: PostgreSQL; ChromaDB is treated as a rebuildable
  semantic index.

## 2. Authentication, registration, and active sessions

**Purpose:** authenticate users through administrator-created accounts, user
self-registration, TOTP delivery, bearer sessions, nonces, and optional client
certificate binding.

**Attributes**

- Passwords use Argon2id PHC strings.
- Basic credentials are exchanged for short-lived bearer tokens.
- Bearer tokens are persisted only as SHA-256 hashes in active sessions.
- Logout deletes/invalidates active sessions.
- Optional `X-Client-Cert-Fingerprint` can bind requests to a certificate.
- State-changing requests use `X-Request-Nonce`.
- Admin-created users can start inactive and registration-incomplete.
- User-owned registration fields include:
  - contact email,
  - optional mobile number,
  - email/mobile verified flags,
  - preferred TOTP delivery channel,
  - verification-code hashes,
  - activation-token hash and expiry.
- Registration sends separate email and SMS codes when both contact methods are
  supplied.
- Activation links are time-limited, with a default 30-minute lifetime.
- Login TOTP is sent through the selected email/SMS channel.

**REST surface**

- `POST /api/v1/auth/token`
- `POST /api/v1/auth/logout`
- `POST /api/v1/auth/check_totp`
- `POST /api/v1/auth/send_totp`
- `POST /api/v1/auth/get_fresh_totp` retained as a backend compatibility route.
- `POST /api/v1/auth/register/start`
- `POST /api/v1/auth/register/verify`
- `GET /api/v1/auth/register/activate`
- `POST /api/v1/users/me/totp/setup`
- `POST /api/v1/users/me/totp/verify`

**UI surface**

- Login mask with user ID/email, password, `Send TOTP`, TOTP code, and sign-in.
- Register-user link and registration mask.
- TOTP configuration panel.
- Admin login uses the same TOTP-delivery flow.

**Key implementation files**

- `backend/app/api_routes/auth.py`
- `backend/app/services/authentication.py`
- `backend/app/services/email_delivery.py`
- `backend/app/services/sms_delivery.py`
- `backend/app/security.py`
- `backend/app/db_models/identity.py`
- `infra/migrations/009_active_user_sessions.sql`
- `infra/migrations/011_registration_delivery.sql`

## 3. User management and authorization

**Purpose:** allow administrators to create, update, deactivate, and grant rights
to users.

**Attributes**

- Roles: student, teacher, staff, administrator.
- Explicit permission list in addition to base role.
- Matriculation number support.
- Admin-created user entries include display name, login email/user ID,
  password, role, permissions, and optional matriculation number.
- Deactivation preserves auditability.
- User creation is available from the administration menu.

**REST surface**

- `POST /api/v1/users`
- `GET /api/v1/users`
- `PATCH /api/v1/users/{user_id}`
- `DELETE /api/v1/users/{user_id}`
- `POST /api/v1/notifications/email`

**UI surface**

- Admin user-definition mask with password confirmation, visibility toggles,
  role selector, permission checkboxes, help dialog, and cancel/create controls.

## 4. Course and enrollment model

**Purpose:** organize users, approved resources, exams, research, and chat by
course and discipline.

**Attributes**

- Course fields: code, title, discipline, description.
- Enrollment rows bind users to courses and roles.
- Course access checks protect research, examinations, and chat.
- Discipline controls grading/search profiles.

**REST surface**

- `GET /api/v1/courses`
- `POST /api/v1/courses`

## 5. Chat, groups, and sharing

**Purpose:** provide course conversations, direct/group chat, exam preparation
rooms, chatbot interaction, and controlled sharing.

**Attributes**

- Conversation types include direct/group style rooms.
- Conversation purpose can identify general, exam-preparation, and exam-work
  contexts.
- Explicit conversation membership protects visibility.
- Messages store body, sender, timestamp, optional attachments, shared type, and
  shared ID.
- Attachments include safe metadata and optional transcripts.
- Chatbot can be addressed with `@chatbot`.
- Users can address other users with `@{user}` style text.
- Research results and practice scores can be shared into chats.
- Random exam groups can be generated per examination/topic.
- Group-exam submissions can use group X.509 certificates.

**REST surface**

- `POST /api/v1/conversations`
- `GET /api/v1/conversations`
- `POST /api/v1/conversations/{conversation_id}/messages`
- `POST /api/v1/conversations/{conversation_id}/messages/upload`
- `GET /api/v1/conversations/{conversation_id}/messages`
- `GET /api/v1/conversations/{conversation_id}/shared-submissions/{submission_id}`
- `GET /api/v1/conversations/{conversation_id}/shared-research/{interaction_id}`
- `POST /api/v1/courses/{course_id}/exam-groups/randomize`
- `PUT /api/v1/exam-groups/{group_id}/certificate`
- WebSocket: `/ws/conversations/{conversation_id}`

**UI surface**

- Chatroom list.
- Chat bubbles for users and chatbot.
- Message input, file attach button, microphone dictation, audio-send button,
  emoji picker, and shared-score/research subwindow controls.

## 6. Research history and query refinement

**Purpose:** store each user’s research and scoring history and reuse recent
context to refine the next query.

**Attributes**

- Histories are separated by user and linked to active login sessions.
- Entries capture hybrid searches, research-question requests, and ASAG scoring.
- Histories can be labeled, stored/pinned, activated/reopened, soft-deleted, or
  newly created as `New chat`.
- Recent high-signal terms are used to refine the next hybrid search query.

**REST surface**

- `GET /api/v1/research/histories`
- `POST /api/v1/research/histories`
- `POST /api/v1/research/histories/{history_id}/activate`
- `PATCH /api/v1/research/histories/{history_id}`
- `DELETE /api/v1/research/histories/{history_id}`
- `GET /api/v1/research/histories/{history_id}/entries`

**UI surface**

- Research-history panel with `New chat`, refresh, label edit, stored checkbox,
  delete, history list, and entry viewer.

**Key implementation files**

- `backend/app/services/research_history.py`
- `infra/migrations/010_research_history.sql`

## 7. Hybrid search, RAG, and knowledge discovery

**Purpose:** retrieve course knowledge from curated documents, videos, and
semantic/full-text indexes.

**Attributes**

- PostgreSQL full-text search.
- BM25 ranking channel.
- ChromaDB semantic search channel.
- Sentence-transformer embeddings.
- Weighted hybrid ranking with explainable score components.
- Discipline-specific search weights.
- Thesaurus expansion for full-text search.
- Apache Solr synonym/thesaurus import support.
- Query expansion metadata returned to clients.
- Coverage warnings for weak source coverage.

**REST surface**

- `GET /api/v1/search`
- `GET /api/v1/search/model-decision`
- `POST /api/v1/research/questions`
- `PATCH /api/v1/research/{interaction_id}/visibility`
- `GET /api/v1/research/history`
- `GET /api/v1/coverage`

**Key implementation files**

- `backend/app/services/search.py`
- `backend/app/services/search_ranking.py`
- `backend/app/services/bm25.py`
- `backend/app/services/embeddings.py`
- `backend/app/services/model_router.py`
- `backend/app/services/research.py`
- `backend/app/services/thesaurus.py`

## 8. Knowledge ingestion, import/export, and vocabulary

**Purpose:** import, approve, index, export, and train from knowledge data.

**Attributes**

- Documents store body text, source URI, metadata, content hash, media type, and
  approval state.
- PDF/text upload and upload-and-ask flows.
- Smart ingestion avoids duplicate content by hash.
- Approved documents are chunked and indexed.
- YouTube resources can be imported/exported with discipline, question tags, and
  keywords.
- Knowledge import bundle support.
- Vocabulary export for model training.
- Fact-check gate for imported knowledge through trusted internet sources when
  configured.

**REST surface**

- `POST /api/v1/documents`
- `POST /api/v1/knowledge/upload`
- `POST /api/v1/knowledge/upload-and-ask`
- `GET /api/v1/knowledge/export.json`
- `GET /api/v1/knowledge/vocabulary.json`
- `GET /api/v1/knowledge/vocab.txt`
- `POST /api/v1/knowledge/import-bundle`
- `POST /api/v1/documents/{document_id}/approve`
- `POST /api/v1/videos`
- `POST /api/v1/videos/{video_id}/approve`
- `GET /api/v1/videos.csv`

## 9. Thesaurus management

**Purpose:** manage terminology expansion for full-text search.

**Attributes**

- Thesauri are stored in PostgreSQL as normalized JSON entries.
- Supported source formats include Apache Solr synonym files and JSON.
- Active thesauri are applied during query expansion.
- Vocabulary export remains available for ML models.

**REST surface**

- `POST /api/v1/thesauri/upload`
- `POST /api/v1/thesauri`
- `GET /api/v1/thesauri`
- `GET /api/v1/thesauri/{thesaurus_id}.json`

**UI surface**

- Admin thesaurus upload mask with name, language, format, and file input.

## 10. ASR and audio input

**Purpose:** allow research and exam-answer input through spoken audio.

**Attributes**

- Browser speech recognition is used when available.
- Project-side ASR fallback transcribes uploaded audio.
- Audio messages can be sent through chat.
- Chatbot can treat audio transcript as command/research context.

**REST surface**

- `POST /api/v1/audio/transcribe`
- `POST /api/v1/conversations/{conversation_id}/messages/upload`

**Key implementation files**

- `backend/app/services/audio.py`
- `frontend/app.js`

## 11. Examination creation and import/export

**Purpose:** create practice and real examinations, including JSON/XML exchange
and AI-assisted drafts.

**Attributes**

- Examinations include title, course, instructions, kind, state, open/close
  dates, group mode, and optional rule set.
- Questions include prompt, reference answer, required keywords, expected facts,
  max score, question type, choices, correct options, and partial-credit flag.
- Instructors can build JSON exams through a GUI mask.
- Exams can be exported/imported as JSON and XML.
- Exam rule sets define page-count, citation, topic, and weight rules.
- AI-assisted draft creation is available for instructors/staff.

**REST surface**

- `POST /api/v1/examinations`
- `POST /api/v1/examinations/draft-with-ai`
- `POST /api/v1/examinations/{examination_id}/release`
- `GET /api/v1/courses/{course_id}/examinations`
- `POST /api/v1/examinations/{examination_id}/questions`
- `POST /api/v1/courses/{course_id}/examinations/from-json`
- `POST /api/v1/courses/{course_id}/examinations/import.json`
- `POST /api/v1/courses/{course_id}/examinations/import.xml`
- `GET /api/v1/examinations/{examination_id}/export.json`
- `GET /api/v1/examinations/{examination_id}/export.xml`
- `POST /api/v1/exam-rule-sets`
- `POST /api/v1/exam-rule-sets/upload`

**UI surface**

- Admin examination builder with `+ Add question`, JSON download, group-mode
  checkbox, question type, choices, correct answers, and points.

## 12. Examination execution and submission

**Purpose:** let students execute practice/real examinations and submit signed,
auditable work.

**Attributes**

- Student exam page loads available exams per course.
- Practice questions can be scored interactively.
- Real-exam checkbox distinguishes real submission from test exam.
- File upload metadata is gathered with answered questions.
- Real submission requires confirmation and a preparation token.
- Submission stores content bytes, content SHA-256, student signature, signing
  certificate, signed timestamp, nonce, state, correction window, retention
  deadline, legal hold, and report data.
- Real-exam resubmission is blocked while correction is in progress.
- Configurable correction window allows limited correction after submission.
- Soft deletion requires override and reason during retention period.

**REST surface**

- `POST /api/v1/submissions/prepare`
- `POST /api/v1/submissions`
- `GET /api/v1/submissions/{submission_id}`
- `DELETE /api/v1/submissions/{submission_id}`
- `POST /api/v1/submissions/{submission_id}/legal-hold`
- `POST /api/v1/submissions/{submission_id}/release-legal-hold`

## 13. ASAG grading and feedback

**Purpose:** score answers with weighted automated short-answer grading while
keeping instructor review and override.

**Attributes**

- Signals include:
  - Jaccard/token overlap,
  - required keyword coverage,
  - sentence-transformer semantic similarity,
  - trained scoring-model signal,
  - fact entailment,
  - contradiction safety,
  - length adequacy.
- Weights are configurable per discipline.
- Missing model signals renormalize remaining weights and flag review.
- Multiple-choice/single-choice scoring is supported.
- Practice scoring produces immediate student feedback.
- Real-exam AI grading is provisional and reviewable.
- Teacher overrides are audited with reason.

**REST surface**

- `POST /api/v1/examinations/{examination_id}/questions/{question_id}/score-draft`
- `POST /api/v1/submissions/{submission_id}/ai-grade`
- `POST /api/v1/submissions/{submission_id}/teacher-override`
- `POST /api/v1/submissions/{submission_id}/return`
- `POST /api/v1/scoring-profiles`
- `GET /api/v1/scoring-profiles`

**UI surface**

- Practice scoring side panel.
- Admin scoring-profile mask with grading and search weights.

## 14. Grading reports and international grade conversions

**Purpose:** generate exam/test reports with scores, feedback, evidence hashes,
and cross-system grade scales.

**Attributes**

- PDF report generation.
- Includes per-question scoring, feedback, evidence hashes, certificate hashes,
  signature hashes, and academic-integrity review details.
- Supports ECTS, German, British, US, and broader European grade conversions.
- Practice reports are AI-only.
- Real reports include instructor return/signature workflow.

**REST surface**

- `GET /api/v1/submissions/{submission_id}/report.pdf`

**Key implementation files**

- `backend/app/services/reports.py`
- `backend/app/services/grading_scales.py`

## 15. Academic integrity, plagiarism, grammar, APA, and fact checks

**Purpose:** review exam work and imported knowledge for quality and originality.

**Attributes**

- APA citation checks.
- Candidate passage selection for internet similarity checks.
- Internet similarity/plagiarism check through configured search API.
- Fact checking against administrator-approved trusted source domains.
- Grammar service hook.
- Academic-integrity review stored on submissions.

**REST surface**

- `POST /api/v1/submissions/{submission_id}/academic-integrity-check`

**Key implementation files**

- `backend/app/services/academic_integrity.py`

## 16. Trust lists, certificates, signatures, OCSP, and private PKI

**Purpose:** validate certificates and signatures against EU, US, and customer
private-trust configurations.

**Attributes**

- ETSI TS 119 612 trusted-list upload.
- EU DSS validation-service contract support.
- Custom private ETSI trust lists.
- US private-PKI and US federal-policy modes.
- Signature validation report storage.
- Private OpenSSL PKI upload/enable flow.
- User certificate assignment and revocation.
- OCSP responder endpoint for private PKI.
- Enabled private roots exportable as PEM for TLS proxy use.

**REST surface**

- `GET /api/v1/trust-lists`
- `POST /api/v1/trust-lists`
- `POST /api/v1/trust-lists/{trust_list_id}/decision`
- `POST /api/v1/signatures/validate`
- `GET /api/v1/private-pki`
- `POST /api/v1/private-pki`
- `POST /api/v1/private-pki/{pki_id}/decision`
- `PUT /api/v1/private-pki/{pki_id}/users/{user_id}/certificate`
- `POST /api/v1/user-certificates/{certificate_id}/revoke`
- `POST /api/v1/ocsp/{pki_id}`
- `GET /api/v1/private-pki-roots.pem`

**Tools**

- `tools/create_private_pki.sh`
- `tools/generate_certificate_request.py`
- `backend/ocsp_signer.py`

## 17. Audit, retention, and legal hold

**Purpose:** preserve traceability for high-value actions and examination
evidence.

**Attributes**

- Audit events record actor, action, target, timestamp, and details.
- Request nonce table prevents replay of state-changing requests.
- Evidence records include hashes, signatures, certificates, and timestamps.
- Ten-year retention period is modeled.
- Legal holds can be applied and released.
- Administrative delete is soft-delete with override and reason.

**Key implementation files**

- `backend/app/db_models/audit.py`
- `backend/app/retention.py`
- `backend/app/services/audit.py`
- `backend/app/services/evidence.py`

## 18. Training data, model training, and scheduler

**Purpose:** prepare approved research/scoring data and run local ML experiments.

**Attributes**

- Training examples store source type, source ID, task, input, target, metadata,
  approval status, and reviewer.
- Training runs store task, model family, status, metrics, report path, and
  timing.
- Nightly/two-day scheduler support.
- Active start-training request endpoint.
- Shortcut mitigation includes shuffling/restructuring/dropout/penalty concepts.
- Early stopping and learning-progress evaluation settings are configurable.
- Free Hugging Face model allowlist.
- CPU/GPU/MPS/auto device selection.

**REST surface**

- `POST /api/v1/training/start`
- `GET /api/v1/training/examples`
- `POST /api/v1/training/examples/{example_id}/decision`
- `GET /api/v1/training/runs`

**Scripts**

- `ml/train_bert.py`
- `ml/train_reranker.py`
- `ml/train_lstm.py`
- `backend/training_job.py`
- `backend/training_scheduler.py`

## 19. Native and packaged clients

**Purpose:** reuse the HTML5 client across web, Android, iOS, macOS, and
Windows.

**Attributes**

- PWA manifest and service worker.
- API base can be injected into bundled client.
- Android/iOS packaging through Capacitor.
- Windows/macOS packaging through Tauri.
- macOS DMG targets for Apple Silicon, Intel, and universal builds.

**Files**

- `frontend/manifest.webmanifest`
- `frontend/sw.js`
- `frontend/client-config.js`
- `clients/native/package.json`
- `clients/native/capacitor.config.ts`
- `clients/native/src-tauri/`
- `tools/build_client_bundle.py`
- `docs/client-app-builds.md`

## 20. Administration GUI

**Purpose:** give administrators browser-based control over users, courses,
chatrooms, trust, PKI, scoring, exams, and search language resources.

**Panels**

- Login with TOTP delivery.
- Course list.
- Defined chatrooms.
- User definition / create user entry.
- TOTP configuration.
- Import/export links.
- Trust-list upload and enable/disable.
- Private PKI upload and enable/disable.
- Discipline scoring profile editor.
- Examination JSON builder.
- Thesaurus/vocabulary management.

**Files**

- `frontend/admin.html`
- `frontend/admin.js`
- `frontend/styles.css`

## 21. Test and performance reporting

**Purpose:** keep architecture, contracts, scoring, search, ingestion, security,
and UI masks verifiable.

**Attributes**

- Route contract tests.
- Database metadata tests.
- ASAG metric tests.
- Search/BM25/vocabulary/ranking tests.
- Thesaurus tests.
- Exam JSON tests.
- Group exam tests.
- Evidence/security/TOTP tests.
- User and exam mask tests.
- Native client build tests.
- Performance tests and JSON/PDF reporting helper.

**Files**

- `tests/`
- `tools/run_test_reports.py`

## 22. Sample data

**Purpose:** provide reviewable course and training examples for development.

**Attributes**

- Computer science sample course: Apple Silicon M3 / microprocessor programming.
- German history sample course: Germany since 1949.
- Synthetic ASAG examples for scoring/training pipeline development.

**Files**

- `data/sample_courses/`
- `data/training/`

## 23. Important operational configuration

**Selected settings**

- `DATABASE_URL`
- `JWT_SECRET`
- `ACCESS_TOKEN_MINUTES`
- `NONCE_TTL_SECONDS`
- `PUBLIC_BASE_URL`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `EMAIL_FROM`
- `SMS_GATEWAY_URL`, `SMS_GATEWAY_TOKEN`
- `REGISTRATION_ACTIVATION_MINUTES`
- `CHROMA_URL`
- `EU_DSS_VALIDATOR_URL`
- `OCSP_SIGNER_URL`, `OCSP_SIGNER_TOKEN`
- `EMBEDDING_PROFILE`
- `COMPUTE_DEVICE`
- `ALLOWED_FREE_MODELS`
- `TRAINING_INTERVAL_HOURS`

## 24. Known implementation boundaries

- SMTP and SMS delivery require deployment configuration.
- EU qualified-signature validation depends on an external DSS service.
- ChromaDB is a derived index and must be rebuilt from PostgreSQL if needed.
- In-process WebSocket broadcasting should be replaced with Redis/NATS before
  multi-replica scaling.
- Legal holds, backups, immutable storage, and certified retention require
  operational controls beyond application code.
- The backend compatibility endpoint `get_fresh_totp` exists, but the login UI
  now uses `send_totp` so TOTP values are delivered through the selected channel
  instead of displayed by the browser button.
