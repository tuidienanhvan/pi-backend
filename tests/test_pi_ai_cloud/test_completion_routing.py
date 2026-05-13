"""T-20260513-001 — Routing optimization tests.

Covers:
  - source_plugin whitelist (validate, raise, normalize)
  - NEW_ROUTING_ENABLED feature flag default
  - KeyAllocator pool method signatures
  - CompletionService NoKeysAvailable error code
  - Package routing fields exist on model
"""

import os

import pytest

from app.core.source_plugin import (
    ALLOWED_SOURCE_PLUGINS,
    InvalidSourcePlugin,
    is_valid,
    validate_source_plugin,
)


# ─── source_plugin whitelist ─────────────────────────────


def test_source_plugin_known_returns_canonical():
    assert validate_source_plugin("pi-seo") == "pi-seo"
    assert validate_source_plugin("pi-chatbot") == "pi-chatbot"
    assert validate_source_plugin("pi-leads") == "pi-leads"
    assert validate_source_plugin("pi-content") == "pi-content"
    assert validate_source_plugin("pi-internal") == "pi-internal"


def test_source_plugin_case_insensitive():
    assert validate_source_plugin("PI-SEO") == "pi-seo"
    assert validate_source_plugin("Pi-ChatBot") == "pi-chatbot"


def test_source_plugin_whitespace_stripped():
    assert validate_source_plugin("  pi-seo  ") == "pi-seo"


def test_source_plugin_empty_defaults_to_internal():
    assert validate_source_plugin("") == "pi-internal"
    assert validate_source_plugin(None) == "pi-internal"


def test_source_plugin_unknown_raises():
    with pytest.raises(InvalidSourcePlugin) as excinfo:
        validate_source_plugin("hacker-plugin")
    assert excinfo.value.code == "invalid_source_plugin"
    assert excinfo.value.status_code == 400


def test_source_plugin_is_valid_helper():
    assert is_valid("pi-seo") is True
    assert is_valid("PI-SEO") is True
    assert is_valid("unknown") is False
    assert is_valid("") is False
    assert is_valid(None) is False


def test_source_plugin_whitelist_contents():
    # Guard against accidental removal of known plugins
    expected = {"pi-seo", "pi-chatbot", "pi-leads", "pi-content", "pi-internal"}
    assert expected.issubset(ALLOWED_SOURCE_PLUGINS)


# ─── Feature flag ─────────────────────────────────────────


def test_new_routing_disabled_by_default(monkeypatch):
    monkeypatch.delenv("PI_AI_NEW_ROUTING_ENABLED", raising=False)
    # Re-import to pick up env change
    import importlib

    from app.pi_ai_cloud.services import completion as comp_mod

    importlib.reload(comp_mod)
    assert comp_mod.NEW_ROUTING_ENABLED is False


def test_new_routing_enabled_when_flag_true(monkeypatch):
    monkeypatch.setenv("PI_AI_NEW_ROUTING_ENABLED", "true")
    import importlib

    from app.pi_ai_cloud.services import completion as comp_mod

    importlib.reload(comp_mod)
    assert comp_mod.NEW_ROUTING_ENABLED is True


def test_new_routing_enabled_accepts_variants(monkeypatch):
    for val in ["1", "TRUE", "yes", "on"]:
        monkeypatch.setenv("PI_AI_NEW_ROUTING_ENABLED", val)
        import importlib

        from app.pi_ai_cloud.services import completion as comp_mod

        importlib.reload(comp_mod)
        assert comp_mod.NEW_ROUTING_ENABLED is True, f"failed for {val!r}"


# ─── KeyAllocator new methods ────────────────────────────


def test_key_allocator_has_pool_methods():
    from app.pi_ai_cloud.services.key_allocator import KeyAllocator

    assert hasattr(KeyAllocator, "auto_allocate_to_license")
    assert hasattr(KeyAllocator, "keys_from_shared_pool")
    assert hasattr(KeyAllocator, "keys_for_license")  # legacy preserved


# ─── Model columns (routing policy) ──────────────────────


def test_ai_package_has_routing_columns():
    from app.pi_ai_cloud.models import AiPackage

    cols = set(AiPackage.__table__.columns.keys())
    assert "routing_mode" in cols
    assert "allowed_tiers" in cols
    assert "priority_boost" in cols
    assert "dedicated_key_count" in cols
    # Legacy columns preserved
    assert "allowed_qualities" in cols
    assert "token_quota_monthly" in cols


def test_routing_mode_default_value():
    from sqlalchemy import inspect

    from app.pi_ai_cloud.models import AiPackage

    col = inspect(AiPackage).columns["routing_mode"]
    # SQLAlchemy default expression
    assert col.default is not None or col.server_default is not None


# ─── CompletionService NoKeysAvailable error ─────────────


def test_no_keys_available_error_code():
    from app.pi_ai_cloud.services.completion import NoKeysAvailable

    exc = NoKeysAvailable()
    assert exc.status_code == 503
    assert exc.code == "no_keys_allocated"
