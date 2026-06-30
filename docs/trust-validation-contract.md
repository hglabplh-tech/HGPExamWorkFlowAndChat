# Trust and signature validation boundary

The Python service does not declare eIDAS qualification by inspecting an X.509
chain itself. It delegates AdES, revocation, timestamp, and qualification
calculation to a separately operated validation service based on European
Commission DSS 6.2 or newer.

Configure its base address as `EU_DSS_VALIDATOR_URL`. The adapter expects:

- `POST /trusted-lists/validate`: validate ETSI TS 119 612 v5/v6 structure,
  XML signature, signing-certificate path, validity period, and status. A private
  list returns `valid_private`; an official list reached through the verified EU
  LOTL may return `valid`.
- `POST /signatures/validate`: validate PAdES, XAdES, CAdES, or JAdES containers,
  certificate paths, historical revocation information, timestamps, signature
  policy, and qualification at signing and validation time.

For `eu_eidas` without custom list IDs, the validator must use the current EU
LOTL, verify its signature against the signing certificates published through
the Official Journal, follow pivot LOTLs, and synchronize Member State lists.
Trusted List v6 must be supported. Network failures must produce an indeterminate
result rather than silently trusting cached or unverified material.

For `custom_etsi`, the list has the same XML structure but is a private trust
decision. It must be signed by a customer-pinned list-signing certificate. It
must never produce the labels “qualified”, “QES”, or “qualified trust service”
unless the service is independently present in an official eIDAS trusted list.

For US profiles, NIST FIPS 186-5 constrains approved digital-signature algorithms
and NIST path/key-management guidance informs policy, but NIST is not a national
commercial root store. `us_private_pki` therefore uses customer trust anchors;
`us_federal_profile` requires the relevant federal PKI policy and trust anchors.
Any commercial WebPKI or sector-specific program must be configured as a distinct
policy rather than being called “NIST trusted”.

The validation response is persisted unchanged alongside its hash, framework,
trusted-list identifiers, validation time, signer identity, outcome, and audit
event. Production reports should include DSS diagnostic and detailed reports,
policy identifiers, revocation evidence, certificate chain, timestamp tokens,
and the trusted-list sequence/version used.

## OCSP

EU validation uses DSS online/cached OCSP and CRL sources and must validate the
response signer, freshness, nonce policy, issuer relationship, and historical
status. Customer private PKIs expose RFC 6960 DER requests at
`/api/v1/ocsp/{private_pki_id}`. The public API supplies database status to the
isolated `backend.ocsp_signer` service, which signs a short-lived response using
a delegated certificate with the `id-kp-OCSPSigning` extended key usage.

The signer configuration is mounted from `ocsp-secrets` using
`infra/ocsp-config.example.json`. Production deployments should replace PEM key
loading with HSM/KMS/PKCS#11 signing, rate-limit the public responder, monitor
freshness, maintain CRLs as a fallback, and preserve revocation audit events.
