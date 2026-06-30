import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes


@dataclass(frozen=True)
class CertificateDetails:
    fingerprint: str
    subject: str
    serial_number: str
    not_valid_before: object
    not_valid_after: object


def certificate_details(pem: bytes) -> CertificateDetails:
    certificate = x509.load_pem_x509_certificate(pem)
    return CertificateDetails(
        fingerprint=certificate.fingerprint(hashes.SHA256()).hex(),
        subject=certificate.subject.rfc4514_string(),
        serial_number=format(certificate.serial_number, "x"),
        not_valid_before=certificate.not_valid_before_utc,
        not_valid_after=certificate.not_valid_after_utc,
    )


def verify_private_chain(leaf_pem: bytes, root_pem: bytes, intermediate_pem: bytes = b"") -> CertificateDetails:
    """Validate time, signatures, CA constraints, and chain with OpenSSL."""
    details = certificate_details(leaf_pem)
    with tempfile.TemporaryDirectory(prefix="study-pki-") as directory:
        directory = Path(directory)
        leaf, root, intermediates = directory / "leaf.pem", directory / "root.pem", directory / "intermediates.pem"
        leaf.write_bytes(leaf_pem)
        root.write_bytes(root_pem)
        intermediates.write_bytes(intermediate_pem)
        command = ["openssl", "verify", "-purpose", "any", "-CAfile", str(root)]
        if intermediate_pem.strip():
            command.extend(["-untrusted", str(intermediates)])
        command.append(str(leaf))
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        if result.returncode:
            raise ValueError(f"Certificate chain validation failed: {result.stderr.strip() or result.stdout.strip()}")
    return details


def verify_root(root_pem: bytes) -> CertificateDetails:
    details = verify_private_chain(root_pem, root_pem)
    certificate = x509.load_pem_x509_certificate(root_pem)
    try:
        constraints = certificate.extensions.get_extension_for_class(x509.BasicConstraints).value
        usage = certificate.extensions.get_extension_for_class(x509.KeyUsage).value
    except x509.ExtensionNotFound as error:
        raise ValueError("Root certificate lacks required CA extensions") from error
    if not constraints.ca or not usage.key_cert_sign or not usage.crl_sign:
        raise ValueError("Root certificate is not authorized to sign certificates and CRLs")
    return details
