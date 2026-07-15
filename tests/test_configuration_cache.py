"""Configuration-cache tests.

Copyright (c) 2026 Harald Glab-Plhak. Licensed under the MIT License.
"""

from backend.app.services.configuration_cache import cache_status, cached_global_settings, invalidate_configuration


def test_global_configuration_cache_can_be_invalidated() -> None:
    """Ensure the configuration cache exposes status and invalidates cleanly."""
    before = cache_status()["versions"]["global"]
    first = cached_global_settings()
    second = cached_global_settings()
    assert first is second
    invalidate_configuration("global")
    after = cache_status()["versions"]["global"]
    assert after == before + 1
    assert cached_global_settings() is not first


def test_complete_configuration_cache_invalidation_increments_known_sections() -> None:
    """Ensure a global cache reset marks every section invalidated."""
    before = cache_status()["versions"]
    invalidate_configuration()
    after = cache_status()["versions"]
    assert all(after[name] == before[name] + 1 for name in before)
