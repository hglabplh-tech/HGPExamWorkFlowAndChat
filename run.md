<!-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. -->

# Running guide

This guide explains how to run `HGPExamWorkFlowAndChat` in Docker and how to
operate the main development and administration workflows.

## Docker quick start

```sh
cd /Users/hglabplh/Documents/Codex/2026-06-30/HGPExamWorkFlowAndChat
cp .env.example .env
```

Edit `.env` for Docker:

```env
DATABASE_URL=postgresql+asyncpg://study:study@postgres:5432/study
CHROMA_URL=http://chroma:8000
JWT_SECRET=replace-with-at-least-32-random-characters
PUBLIC_BASE_URL=https://localhost
```

Create local TLS files if needed:

```sh
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout certs/server.key \
  -out certs/server.crt \
  -days 365 \
  -subj "/CN=localhost"
```

Start:

```sh
docker compose up --build
```

Bootstrap the first administrator:

```sh
docker compose exec api python -m backend.app.bootstrap admin@example.org "a-long-password" --name "Administrator" --role admin
```

Open:

- Web app: `https://localhost`
- Admin app: `https://localhost/admin`
- API docs: `https://localhost/docs`
- Health: `https://localhost/health`
- Readiness: `https://localhost/ready`

## Daily Docker commands

Show services:

```sh
docker compose ps
```

Follow API logs:

```sh
docker compose logs -f api
```

Stop while keeping data:

```sh
docker compose down
```

Stop and remove PostgreSQL, ChromaDB, and model volumes:

```sh
docker compose down -v
```

Use `down -v` only when you intentionally want to delete local Docker data.

## Admin configuration after login

Open `https://localhost/admin` and sign in as an administrator.

Useful menu entries:

- `User definition`: create administrator, instructor, staff, and student users.
- `TOTP configuration`: initialize two-factor login for the signed-in account.
- `SMTP / IMAP configuration`: configure outbound SMTP and stored IMAP settings.
- `Logging configuration`: choose `WARNING`, `ERROR`, `SEVERE`, `INFO`, or
  `DEBUG`, optionally write to a logfile, and enable sanitized debug values.
- `Configuration cache`: view cached configuration sections or invalidate them
  manually. Normal admin saves invalidate their affected section automatically.
- `Import/export`: export knowledge and vocabulary files.
- `Rebuild ChromaDB`: rebuild the vector index from PostgreSQL.
- `Trusted lists` and `Private PKI`: configure certificate trust sources.

The SMTP/IMAP page stores:

- SMTP host, port, username, password, STARTTLS/SSL mode, sender address, and
  support address.
- IMAP host, port, username, password, and SSL mode.

Saved SMTP settings override `.env` for application email delivery. Empty
password fields keep the previously saved password.

Logging uses Python's built-in `logging`. The default is `WARNING`, so warning,
error, and severe/critical messages are visible. Enable `INFO` only when you
want HTTP RPC entry/exit traces; enable `DEBUG` only for troubleshooting because it
adds sanitized request/response metadata.

The application reads active configuration through a lazy configuration cache.
Mail settings and scoring profiles are loaded once, reused, and reloaded only
after an administrator changes the affected section or invalidates the cache.

## Authentication flow

1. An administrator creates the user.
2. The user starts registration from the login page.
3. The system sends email and optional SMS verification codes.
4. The user verifies the codes and receives a 30-minute activation link.
5. The user activates the account.
6. The user enters email/password, presses `Send TOTP`, enters the TOTP, and
   logs in.
7. The backend creates a persistent active-session row and returns a bearer
   token.
8. State-changing HTTP RPC calls send `Authorization: Bearer ...` and a unique
   `X-Request-Nonce`.

## Rebuild ChromaDB from PostgreSQL

From the admin UI:

1. Open `Rebuild ChromaDB`.
2. Choose `Economy` or `Quality`.
3. Press `Rebuild ChromaDB`.

RPC-over-HTTP endpoint:

```text
POST /api/v1/knowledge/rebuild-chroma?profile=economy
```

Course knowledge-base entry points:

```text
GET /api/v1/courses/{course_id}/knowledge-base
PUT /api/v1/courses/{course_id}/knowledge-base/{name}
```

These rows tell the application where a course starts its PostgreSQL full-text,
BM25, and mBERT/semantic search configuration.

In course chats, only a message whose first token is `@chatbot` invokes this
course-scoped hybrid search. Other `@user`, `@"User Name"`, and `@{User Name}`
forms are treated as user mentions and saved with the chat message.

## Database CLI and Playground initialization

Create schema, apply SQL migrations, and initialize the Playground course:

```sh
python -m backend.app.db_cli bootstrap-playground
```

Only initialize Playground after configuring `DATABASE_URL` for the intended
PostgreSQL database.

If RSA-capable X.509 recipient certificates are present, exam answers, signed
exam content, ASAG proposals, and returned teacher grades are additionally stored
as AES-256-GCM/RSA-OAEP encrypted JSONB envelopes for the relevant
student/instructor or group recipients.

Example:

```sh
curl -k -X POST "https://localhost/api/v1/knowledge/rebuild-chroma?profile=economy" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "X-Request-Nonce: $(uuidgen)"
```

## Playground ASAG experiments

Use the `Playground` discipline/course to try ASAG weights without changing
normal course grading.

Endpoints:

```text
GET  /api/v1/playground/course
POST /api/v1/playground/asag-score
POST /api/v1/playground/asag-metrics
```

`asag-score` accepts request-level weight/topic/context overrides and stores the
input as an unapproved training candidate. `asag-metrics` compares trials by
accuracy, MAE, RMSE, latency, and optional baseline accuracy.

## Import and export knowledge

Useful endpoints:

```text
POST /api/v1/knowledge/upload
POST /api/v1/knowledge/upload-and-ask
GET  /api/v1/knowledge/export.json
POST /api/v1/knowledge/import-bundle
GET  /api/v1/knowledge/vocab.txt
GET  /api/v1/knowledge/vocabulary.json
POST /api/v1/thesauri/upload
POST /api/v1/thesauri
```

PostgreSQL is canonical. ChromaDB can always be rebuilt from approved
PostgreSQL knowledge data.

## Training jobs

Run one training job:

```sh
docker compose --profile tools run --rm trainer
```

Run the scheduler:

```sh
docker compose --profile training up training-scheduler
```

The default interval is `TRAINING_INTERVAL_HOURS=48`, so scheduled training
runs every two days.

## Local development without Caddy

Use localhost values in `.env`:

```env
DATABASE_URL=postgresql+asyncpg://study:study@localhost:5432/study
CHROMA_URL=http://localhost:8001
```

Start data services:

```sh
docker compose up postgres chroma
```

Install dependencies:

```sh
python -m pip install -e '.[dev,ml]'
```

Run the API:

```sh
python -m uvicorn backend.app.main:app --reload
```

Or:

```sh
make run
```

Never expose the raw Uvicorn development port directly to the public internet.

## Tests and reports

Run tests:

```sh
python -m pytest -q
```

Run the project check:

```sh
make check
```

Generate report artifacts:

```sh
python tools/run_test_reports.py
```

## Native clients

Build the static client bundle:

```sh
export HCP_API_BASE="https://study.example.edu"
make client-bundle
```

Platform builds:

```sh
make client-android-sync
make client-ios-sync
make client-macos-dmg-silicon
make client-macos-dmg-intel
make client-macos-dmg-universal
make client-windows-build
```

See `docs/client-app-builds.md` for platform prerequisites.

## Production notes

- Put the API behind Caddy, Kubernetes ingress, or another TLS 1.2/1.3 reverse
  proxy.
- Do not expose Uvicorn directly.
- Store secrets in a real secrets manager.
- Use managed PostgreSQL or a hardened PostgreSQL deployment with backups.
- Treat ChromaDB as a derived index.
- Move schema creation from API startup to reviewed migration jobs.
- Use Redis or NATS for WebSocket fan-out before running multiple API replicas.
- Review legal hold, retention, audit, and deletion workflows operationally.

## Troubleshooting

Certificate warning: the local self-signed certificate is not trusted by the
browser. Trust it locally or use a real certificate.

SMTP/TOTP failure: check `/admin`, `SMTP / IMAP configuration`, and API logs:

```sh
docker compose logs -f api
```

Database connection failure inside Docker: use `postgres` as host in
`DATABASE_URL`.

ChromaDB failure inside Docker: use `http://chroma:8000` as `CHROMA_URL`.

Rejected state-changing request: include both the bearer token and a fresh
`X-Request-Nonce`.
