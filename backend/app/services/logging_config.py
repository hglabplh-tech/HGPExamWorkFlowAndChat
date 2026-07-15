# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""Simple standard-library logging configuration for the application."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "SEVERE": logging.CRITICAL,
    "CRITICAL": logging.CRITICAL,
}

SENSITIVE_NAMES = {
    "authorization",
    "cookie",
    "password",
    "token",
    "totp",
    "signature",
    "certificate",
    "secret",
    "nonce",
    "x-totp-code",
    "x-request-nonce",
    "x-client-cert-fingerprint",
}

_current_config: dict[str, Any] = {
    "level": "WARNING",
    "log_file_path": None,
    "debug_values": False,
}


def normalize_level(level: str | None) -> str:
    """Return a supported logging level name and accept SEVERE as CRITICAL."""
    normalized = (level or "WARNING").strip().upper()
    if normalized not in LOG_LEVELS:
        raise ValueError(f"Unsupported log level: {level}")
    return "SEVERE" if normalized == "CRITICAL" else normalized


def configure_logging(level: str | None = None, log_file_path: str | None = None, debug_values: bool | None = None) -> dict[str, Any]:
    """Configure root logging with timestamps using Python's standard logging library."""
    selected = normalize_level(level or _current_config["level"])
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file_path:
        Path(log_file_path).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file_path))
    logging.basicConfig(
        level=LOG_LEVELS[selected],
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
        handlers=handlers,
    )
    _current_config.update(
        {
            "level": selected,
            "effective_level": logging.getLevelName(LOG_LEVELS[selected]),
            "log_file_path": log_file_path,
            "debug_values": bool(debug_values) if debug_values is not None else bool(_current_config["debug_values"]),
            "available_levels": ["DEBUG", "INFO", "WARNING", "ERROR", "SEVERE"],
        }
    )
    logging.getLogger(__name__).info("logging_configured level=%s file=%s", selected, log_file_path or "console")
    return current_logging_config()


def current_logging_config() -> dict[str, Any]:
    """Return the current runtime logging configuration."""
    return dict(_current_config, available_levels=["DEBUG", "INFO", "WARNING", "ERROR", "SEVERE"])


def sanitize_mapping(values: dict[str, Any] | None) -> dict[str, Any]:
    """Redact tokens, passwords, certificates, signatures, and nonces before debug logging."""
    sanitized: dict[str, Any] = {}
    for key, value in (values or {}).items():
        lowered = key.lower()
        if any(secret_name in lowered for secret_name in SENSITIVE_NAMES):
            sanitized[key] = "***redacted***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_mapping(value)
        elif isinstance(value, (list, tuple)):
            sanitized[key] = [sanitize_mapping(item) if isinstance(item, dict) else item for item in value[:20]]
        else:
            sanitized[key] = value
    return sanitized
