# Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""SMS delivery adapter for registration and TOTP codes."""
import httpx

from ..config import get_settings


async def send_sms(number: str, message: str) -> None:
    """Send one SMS through the configured HTTP SMS gateway."""
    settings = get_settings()
    if not settings.sms_gateway_url:
        raise RuntimeError("SMS_GATEWAY_URL is not configured")
    headers = {}
    token = settings.sms_gateway_token.get_secret_value()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(settings.sms_gateway_url, json={"to": number, "message": message}, headers=headers)
        response.raise_for_status()
