<!-- Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License. -->

# Synthetic training data

These small datasets demonstrate the schema used by the nightly answer-scoring job. They are synthetic, contain no personal data, and are suitable for tests and pipeline experiments—not production model approval. A subject specialist should verify facts, balance labels, add source citations, and create separate train, validation, and test partitions before training.

`normalized_score` ranges from 0 to 1. Production imports should retain provenance, consent, visibility, and anonymization metadata and must never train on private exam or chat content merely because it exists in PostgreSQL.
