"""REST-client behavior tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

import httpx

from clients.rest_client import HGPExamWorkFlowAndChatClient


def test_client_logs_in_and_adds_a_fresh_nonce(monkeypatch) -> None:
    """Ensure state-changing requests carry a bearer token and anti-replay nonce."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        """Return deterministic responses while retaining each request for assertions."""
        requests.append(request)
        payload = {"access_token": "test-token"} if request.url.path.endswith("/auth/token") else {"id": "course"}
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    original_client = httpx.Client
    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(transport=transport, base_url=kwargs["base_url"]),
    )
    client = HGPExamWorkFlowAndChatClient("https://service.example", "a@example.org", "secret")
    assert client.create_course("CS", "Course", "Computing") == {"id": "course"}
    assert requests[-1].headers["Authorization"] == "Bearer test-token"
    assert len(requests[-1].headers["X-Request-Nonce"]) >= 24
