# Study Harbour

A cloud-ready Python service for course chat, curated documents and videos,
hybrid search, secure examination submissions, assisted grading, and independent
ML experiments. The project is currently **alpha software**, not a certified
grading, qualified-signature, or records-management product.

Copyright © 2026 Harald Glab-Plhak. Distributed under the MIT License.

## Boundaries

- `frontend/`: responsive HTML5 Progressive Web App (one UI for phones, tablets, and desktops)
- `backend/app/api.py`: versioned REST boundary
- `backend/app/services/`: indexing and retrieval algorithms
- `backend/app/models.py`: PostgreSQL source-of-truth model
- `clients/`: independent Python REST client
- `ml/`: BERT fine-tuning and educational LSTM training
- `infra/`: TLS proxy and database setup

ChromaDB is a derived semantic index. PostgreSQL remains canonical, including
approval status and provenance, so the index can always be rebuilt and audited.

## Run locally

1. Copy `.env.example` to `.env` and replace `JWT_SECRET`.
2. Put a development certificate and key in `certs/server.crt` and `certs/server.key`.
3. Run `docker compose up --build`.
4. Create the first administrator inside the API container:
   `python -m backend.app.bootstrap admin@example.org 'a-long-password'`.
5. Open `https://localhost`. Interactive API documentation is at `/docs`.

For development without TLS termination, run PostgreSQL and Chroma with Compose,
then start `uvicorn backend.app.main:app --reload`. Never expose that port publicly.

## Build and deployment

The application is packaged as an OCI/Docker image containing Python 3.12,
FastAPI, Uvicorn, OpenSSL, and all runtime dependencies. Use Docker Compose for
development or a single-server installation:

```sh
cp .env.example .env
make up
```

For cloud production, push a version tag to publish an image to GitHub Container
Registry, replace `OWNER` and the example host names in `deploy/kubernetes/`,
create the application and OCSP secrets, and apply the manifests. Kubernetes is
language-neutral; a Deployment is appropriate for the stateless Python API,
while PostgreSQL, Chroma, object storage, and model storage should be managed
services or separately operated stateful workloads.

The provided deployment starts with one API replica. Before scaling out, replace
the in-process WebSocket room broadcaster with Redis/NATS pub-sub, move startup
schema changes to an Alembic migration Job, and use shared model/object storage.
The GitHub workflows test Python 3.11/3.12, build the image, and publish tagged
releases to GHCR with provenance and an SBOM.

## Authentication and TLS

Basic authentication is accepted only to exchange credentials for a short-lived
bearer token. Every state-changing request also needs a unique
`X-Request-Nonce`. The included Caddy configuration permits TLS 1.2 and 1.3 and
contains an optional mutual-certificate authentication block. In production use
an institutional OpenID Connect provider, managed certificates, refresh-token
rotation, and a shared nonce store such as Redis.

TLS is never replaced by Basic authentication, tokens, nonces, hashes, or digital
signatures: those mechanisms have different jobs. Client certificates can be
enabled in `infra/Caddyfile`; Caddy then forwards the verified certificate
fingerprint to the otherwise private API. Passwords use Argon2id and are stored
in the self-describing Unix/PHC modular format (`$argon2id$...`), not a legacy
DES/SHA `/etc/shadow` scheme.

## Signed examination evidence and retention

Before submission, a student registers an Ed25519 public key. Their device signs
a canonical receipt containing the exam ID, student ID, SHA-256 content digest,
client timestamp, and one-time nonce. PostgreSQL stores the original bytes,
signature, digest, nonce, server receipt timestamp, and retention deadline.
Database triggers reject mutation or physical deletion of evidence and reject
all updates/deletes to the hash-chained audit log.

The administrative delete endpoint is deliberately a soft deletion: it requires
an explicit retention override plus a reason during an active ten-year period,
records the administrator, and preserves the evidence. Actual legally compliant
purging must be a separately approved operational workflow coordinated with
backups and immutable object storage; application code alone cannot guarantee a
legal hold or make a system impossible to compromise.

Direct and group conversations have explicit membership rows. A submission may
only be shared by its owner, and its content endpoint requires membership in the
exact conversation where it was shared.

## EU and US trust frameworks

The `/admin` screen manages customer trusted lists in ETSI TS 119 612 v5/v6
XML. Lists remain disabled until their XML signature is validated. Official EU
status cannot be set by an administrator; eIDAS validation follows the official
EU LOTL through an EU DSS 6.2+ validation service. See
`docs/trust-validation-contract.md` for its small HTTP contract and required
fail-closed behavior.

The signature API records PAdES/XAdES/CAdES/JAdES validation reports and supports
official EU, customer-private ETSI, US private-PKI, and US federal-policy modes.
NIST defines cryptographic and key-management requirements, not a universal US
root list. A customer root therefore establishes private trust, not eIDAS
qualified status or automatic US government trust.

`tools/generate_certificate_request.py` creates an encrypted ECDSA P-256 key and
CSR. The CSR must be certified by the selected CA, federal PKI, or qualified EU
trust service provider. Local key generation alone cannot create a qualified
electronic signature certificate.

Customers may instead operate a private OpenSSL PKI. Run
`tools/create_private_pki.sh <directory> <user-common-name>` to generate an
encrypted P-256 root, issuing intermediate, and user client certificate with CA
and key-usage constraints. Upload the root and intermediate through the private
PKI administration API, enable it with an audited decision, then assign the
verified user certificate. The `/api/v1/private-pki-roots.pem` API exports all
enabled roots as `customer-client-roots.pem`; mount that file into Caddy and reload Caddy after
changing the trust set. Never place root or intermediate private keys on the
application server.

OpenSSL chain validity means “trusted by this customer configuration.” It does
not imply eIDAS qualified, public WebPKI, or US federal status. Revocation lists,
OCSP, key ceremonies, offline root protection, renewal, and compromise response
remain required production PKI procedures.

The private-PKI generator also creates a delegated OCSP responder certificate
and encrypted key. Configure the isolated signer using
`infra/ocsp-config.example.json`, set `OCSP_SIGNER_URL` and its separate service
token, and put the final `/api/v1/ocsp/{private-pki-id}` URL into issued user
certificates. The responder returns RFC 6960 `good`, `revoked`, or `unknown`
states and echoes OCSP nonces. EU certificates and signatures use DSS-managed
OCSP/CRL validation instead.

## Knowledge and coverage

Documents and YouTube resources enter an unapproved review queue. Search returns
only approved material. Empty searches emit a coverage warning, which is the
beginning of a staff dashboard for disciplines, courses, and questions with weak
or missing source coverage.

The YouTube discovery helper writes unapproved candidates to CSV:

```sh
YOUTUBE_API_KEY=... python tools/youtube_to_csv.py \
  "cellular respiration tutorial" biology-videos.csv --discipline Biology
```

## ML experiments

Install the optional packages with `pip install -e '.[ml]'`.

Fine-tune a BERT-compatible classifier from a `text,label` CSV:

```sh
python ml/train_bert.py training.csv --labels 8
```

Train a multilingual query/passage reranker from `query,passage,label` CSV data:

```sh
python ml/train_reranker.py relevance.csv --family xlm-roberta
```

Train the small character-level LSTM:

```sh
python ml/train_lstm.py approved-corpus.txt
```

The LSTM is deliberately isolated from grading and factual RAG responses: it is
useful for learning and controlled experiments, but it does not provide reliable
facts or citations. Models should be evaluated and registered before deployment.

Hybrid retrieval fuses PostgreSQL full-text results with Chroma semantic results.
The model router uses a multilingual MiniLM sentence transformer on economical
hardware, a larger multilingual MPNet profile when selected, and optionally
reranks complex queries with mBERT or XLM-RoBERTa. Device selection supports
`auto`, `cpu`, `cuda`, `mps`, or an installed PyTorch/XLA device. BERT-family
models are used for contextual reranking; sentence transformers produce the
retrieval embeddings.

Sentence-BERT (SBERT) is the sentence-embedding architecture; Sentence
Transformers is the library and broader model ecosystem used here to run it.
The ASAG implementation calls `SentenceTransformer` directly, so semantic answer
comparison is not limited to a single original SBERT checkpoint.

## Weighted ASAG grading and hybrid ranking

The administration screen creates immutable, versioned scoring profiles for each
discipline. Grading profiles combine token Jaccard overlap, required-keyword
coverage, multilingual sentence-transformer cosine similarity, expected-fact
entailment, contradiction safety, and answer-length adequacy. Every question has
a teacher reference answer, required concepts, approved facts, and maximum mark.

`POST /api/v1/submissions/{id}/ai-grade` creates a provisional score containing
every raw signal, configured weight, actually applied normalized weight, profile
version, warning, and review flag. If a model signal is unavailable, remaining
weights are renormalized and the result is flagged; a teacher still approves or
overrides the grade. Large disagreement between signals also forces review.

The same discipline profile controls search ranking. PostgreSQL full-text and
Chroma sentence-transformer results are normalized independently, multiplied by
their configured weights, and summed. Each search result returns
`score_components`, making its final rank explainable.

## Production work still required

- Alembic migrations instead of automatic table creation
- Redis/NATS-backed WebSocket fan-out before multiple API replicas
- background jobs for ASR, embeddings, Chroma indexing, and virus scanning
- object storage for original documents and exam files
- calibrated per-discipline grading against teacher-labelled evaluation sets
- complete RAG answer generation, citations, ASR, and model monitoring
- retention rules, consent, accessibility testing, backups, and monitoring
