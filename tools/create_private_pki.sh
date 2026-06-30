#!/bin/sh
# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
set -eu

OUT="${1:-private-pki}"
USER_CN="${2:-student@example.org}"
export OCSP_URL="${3:-https://example.invalid/api/v1/ocsp/replace-with-private-pki-id}"
mkdir -p "$OUT"
umask 077

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -aes-256-cbc -out "$OUT/root-key.pem"
openssl req -new -x509 -sha256 -days 3650 -key "$OUT/root-key.pem" \
  -subj "/C=DE/O=Customer Private PKI/CN=Customer Root CA" \
  -config infra/openssl/openssl.cnf -extensions root_ca -out "$OUT/root-cert.pem"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -aes-256-cbc -out "$OUT/intermediate-key.pem"
openssl req -new -sha256 -key "$OUT/intermediate-key.pem" \
  -subj "/C=DE/O=Customer Private PKI/CN=Customer Issuing CA" -out "$OUT/intermediate.csr.pem"
openssl x509 -req -sha256 -days 1825 -in "$OUT/intermediate.csr.pem" \
  -CA "$OUT/root-cert.pem" -CAkey "$OUT/root-key.pem" -CAcreateserial \
  -extfile infra/openssl/openssl.cnf -extensions intermediate_ca -out "$OUT/intermediate-cert.pem"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -aes-256-cbc -out "$OUT/user-key.pem"
openssl req -new -sha256 -key "$OUT/user-key.pem" \
  -subj "/C=DE/O=Customer Private PKI/CN=$USER_CN" -out "$OUT/user.csr.pem"
openssl x509 -req -sha256 -days 825 -in "$OUT/user.csr.pem" \
  -CA "$OUT/intermediate-cert.pem" -CAkey "$OUT/intermediate-key.pem" -CAcreateserial \
  -extfile infra/openssl/openssl.cnf -extensions user_client -out "$OUT/user-cert.pem"

openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -aes-256-cbc -out "$OUT/ocsp-key.pem"
openssl req -new -sha256 -key "$OUT/ocsp-key.pem" \
  -subj "/C=DE/O=Customer Private PKI/CN=Customer OCSP Responder" -out "$OUT/ocsp.csr.pem"
openssl x509 -req -sha256 -days 825 -in "$OUT/ocsp.csr.pem" \
  -CA "$OUT/intermediate-cert.pem" -CAkey "$OUT/intermediate-key.pem" -CAcreateserial \
  -extfile infra/openssl/openssl.cnf -extensions ocsp_responder -out "$OUT/ocsp-cert.pem"

openssl verify -CAfile "$OUT/root-cert.pem" -untrusted "$OUT/intermediate-cert.pem" "$OUT/user-cert.pem"
printf '%s\n' "Private PKI created in $OUT. Protect keys offline; distribute only certificates."
