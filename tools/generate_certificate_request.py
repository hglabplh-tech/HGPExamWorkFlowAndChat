"""Generate a protected ECDSA key and CSR for a CA/QTSP to certify.

This creates no eIDAS-qualified or federally trusted certificate by itself.
"""
import argparse
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--common-name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--organization", required=True)
    parser.add_argument("--country", required=True, help="Two-letter country code")
    parser.add_argument("--key-out", default="identity-key.pem")
    parser.add_argument("--csr-out", default="identity.csr.pem")
    args = parser.parse_args()
    password = input("Private-key password: ").encode()
    if len(password) < 12:
        raise SystemExit("Use a password of at least 12 characters")

    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, args.country.upper()),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, args.organization),
        x509.NameAttribute(NameOID.COMMON_NAME, args.common_name),
        x509.NameAttribute(NameOID.EMAIL_ADDRESS, args.email),
    ])
    request = x509.CertificateSigningRequestBuilder().subject_name(subject).sign(key, hashes.SHA256())
    Path(args.key_out).write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(password),
    ))
    Path(args.csr_out).write_bytes(request.public_bytes(serialization.Encoding.PEM))
    print(f"Created protected key {args.key_out} and certificate request {args.csr_out}")


if __name__ == "__main__":
    main()
