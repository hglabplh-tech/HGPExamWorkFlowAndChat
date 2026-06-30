# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Utilities for trust."""
import base64
import hashlib
from dataclasses import dataclass

import httpx
from defusedxml import ElementTree

from ..config import get_settings


@dataclass(frozen=True)
class ParsedTrustList:
    """Represent parsedtrustlist."""
    content: bytes
    sha256: str
    version: int | None
    scheme_territory: str | None


def parse_etsi_trust_list(content: bytes) -> ParsedTrustList:
    """Perform the parse etsi trust list operation."""
    if len(content) > 25 * 1024 * 1024:
        raise ValueError("Trusted list exceeds the 25 MiB limit")
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise ValueError("Trusted list is not well-formed XML") from error
    if root.tag.split("}")[-1] != "TrustServiceStatusList":
        raise ValueError("XML is not an ETSI TrustServiceStatusList")
    values: dict[str, str] = {}
    for element in root.iter():
        local_name = element.tag.split("}")[-1]
        if local_name in {"TSLVersionIdentifier", "SchemeTerritory"} and element.text:
            values[local_name] = element.text.strip()
    try:
        version = int(values["TSLVersionIdentifier"])
    except (KeyError, ValueError):
        version = None
    if version not in {5, 6}:
        raise ValueError("Only ETSI Trusted List versions 5 and 6 are accepted")
    return ParsedTrustList(
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        version=version,
        scheme_territory=values.get("SchemeTerritory"),
    )


class TrustValidator:
    """Adapter for a separately deployed EU DSS 6.2+ validation service.

    Python owns policy, persistence, and audit. DSS owns AdES, revocation,
    timestamp, LOTL/TL signature, and qualification calculations.
    """

    def __init__(self) -> None:
        """Perform the init operation."""
        settings = get_settings()
        if not settings.eu_dss_validator_url:
            raise RuntimeError("EU_DSS_VALIDATOR_URL is not configured")
        self.base_url = settings.eu_dss_validator_url.rstrip("/")
        self.timeout = settings.trust_validation_timeout_seconds

    async def validate_trust_list(self, content: bytes, framework: str) -> dict:
        """Perform the validate trust list operation."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/trusted-lists/validate",
                json={"xml_base64": base64.b64encode(content).decode(), "framework": framework},
            )
            response.raise_for_status()
            return response.json()

    async def validate_signature(
        self,
        signed_document: bytes,
        signature_format: str,
        framework: str,
        trust_lists: list[bytes],
        validation_time: str | None,
    ) -> dict:
        """Perform the validate signature operation."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/signatures/validate",
                json={
                    "signed_document_base64": base64.b64encode(signed_document).decode(),
                    "signature_format": signature_format,
                    "framework": framework,
                    "trusted_lists_base64": [base64.b64encode(item).decode() for item in trust_lists],
                    "validation_time": validation_time,
                },
            )
            response.raise_for_status()
            return response.json()

