<!-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. -->

# Installation guide

This guide explains how to install and configure `HGPExamWorkFlowAndChat`.
Docker Compose is the recommended installation path because the application
uses FastAPI, PostgreSQL with pgvector, ChromaDB, Caddy TLS termination, and
optional OCSP/training services.

The project is alpha software. It is a technical foundation for course
collaboration, hybrid search, ASAG scoring, secure submissions, and model
training; it is not by itself a certified grading, legal-hold, or qualified
signature product.

## Prerequisites

- Docker Desktop or Docker Engine with Docker Compose v2.
- Git.
- OpenSSL for local certificates and private-PKI test material.
- Optional: GNU Make for the shortcuts in `Makefile`.
- Optional for local development: Python 3.11 or newer. The Docker image uses
  Python 3.12.
- Optional for native clients: Android Studio, Xcode, Node.js, and Rust as
  described in `docs/client-app-builds.md`.

## Project root

Use this directory:

```sh
cd /Users/hglabplh/Documents/Codex/2026-06-30/HGPExamWorkFlowAndChat
```

Main directories:

- `backend/`: FastAPI app, REST routes, services, security, scoring, search,
  workflows, and database models.
- `frontend/`: HTML5 web app and admin UI.
- `infra/`: Caddy, PostgreSQL initialization, migrations, and OCSP examples.
- `clients/`: Python REST client and native wrapper projects.
- `ml/`: BERT/reranker/LSTM training utilities.
- `data/`: sample courses and synthetic training data.

## Configure `.env`

Create the private environment file:

```sh
cp .env.example .env
```

For Docker Compose, set service-internal addresses:

```env
DATABASE_URL=postgresql+asyncpg://study:study@postgres:5432/study
CHROMA_URL=http://chroma:8000
JWT_SECRET=replace-with-at-least-32-random-characters
PUBLIC_BASE_URL=https://localhost
```

For local development outside Docker, localhost is used instead:

```env
DATABASE_URL=postgresql+asyncpg://study:study@localhost:5432/study
CHROMA_URL=http://localhost:8001
```

Important configuration groups:

- Authentication: `ACCESS_TOKEN_MINUTES`, `NONCE_TTL_SECONDS`,
  `PASSWORD_AUTH_ENABLED`, `CLIENT_CERTIFICATE_AUTH_ENABLED`.
- Registration and TOTP delivery: `SMTP_*`, `EMAIL_FROM`, `SMS_GATEWAY_URL`,
  `SMS_GATEWAY_TOKEN`, `REGISTRATION_ACTIVATION_MINUTES`.
- Search/model routing: `EMBEDDING_PROFILE`, `COMPUTE_DEVICE`,
  `ALLOWED_FREE_MODELS`, `AUDIO_MODEL`, `INFERENCE_TIMEOUT_SECONDS`.
- Training: `TRAINING_INTERVAL_HOURS`, `TRAINING_EPOCHS`,
  `TRAINING_LEARNING_RATE`, `TRAINING_DROPOUT`, `MODEL_OUTPUT_DIR`.
- Trust/signatures: `EU_DSS_VALIDATOR_URL`, `OCSP_SIGNER_URL`,
  `OCSP_SIGNER_TOKEN`, `SIGNATURE_HASH_ALGORITHM`, `SIGNATURE_ALGORITHMS`,
  `RETENTION_YEARS`.

Playground ASAG experiments do not need extra installation steps. They use the
built-in `Playground` course/discipline and store request inputs as unapproved
training candidates for later staff review.

SMTP can also be configured after login through the admin menu item
`SMTP / IMAP configuration`. Values saved there override `.env` for outgoing
mail while keeping `.env` as fallback.

## Create local TLS certificates

Caddy expects:

```text
certs/server.crt
certs/server.key
```

For local development only:

```sh
mkdir -p certs
openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout certs/server.key \
  -out certs/server.crt \
  -days 365 \
  -subj "/CN=localhost"
```

Production deployments should use certificates from the institution, cloud
provider, public CA, or approved private PKI. Mutual TLS can be enabled in
`infra/Caddyfile` by uncommenting the `client_auth` block and mounting
`certs/customer-client-roots.pem`.

## Docker services

`docker-compose.yml` defines:

- `postgres`: PostgreSQL 16 with pgvector.
- `chroma`: ChromaDB.
- `api`: FastAPI/Uvicorn application.
- `caddy`: TLS 1.2/1.3 reverse proxy.
- `ocsp-signer`: optional private-PKI OCSP signer.
- `trainer`: optional one-shot training job under the `tools` profile.
- `training-scheduler`: optional two-day training scheduler under the
  `training` profile.

Persistent volumes:

- `postgres_data`
- `chroma_data`
- `model_data`

## Install and start

Build and run the default stack:

```sh
docker compose up --build
```

Or:

```sh
make up
```

The prototype creates starter tables and retention triggers during API startup.
For formal production use, replace that startup behavior with reviewed Alembic
migration jobs using the SQL files in `infra/migrations/`.

## Create the first administrator

After the API is running:

```sh
docker compose exec api python -m backend.app.bootstrap admin@example.org "a-long-password" --name "Administrator" --role admin
```

Then open:

```text
https://localhost/admin
```

Use the admin menu to create users, configure TOTP, configure SMTP/IMAP, manage
trusted lists, import knowledge, and rebuild ChromaDB.

## Installation checklist

- `.env` contains production-strength secrets.
- Docker `.env` uses `postgres` and `chroma` service names.
- TLS certificate files exist.
- The first administrator exists.
- SMTP/IMAP settings are configured if registration/TOTP delivery is needed.
- `/health` and `/ready` return success.
- PostgreSQL backups and restore tests are planned.
- ChromaDB is treated as rebuildable from PostgreSQL.
- Legal-hold and retention procedures are reviewed operationally, not only in
  application code.
