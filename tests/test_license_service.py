"""Unit tests for license helpers — pure functions."""

from app.shared.license.service import LicenseService


def test_normalise_domain_strips_scheme() -> None:
    assert LicenseService._normalise_domain("https://example.com") == "example.com"
    assert LicenseService._normalise_domain("http://example.com/page") == "example.com"


def test_normalise_domain_strips_www() -> None:
    assert LicenseService._normalise_domain("https://www.example.com") == "example.com"


def test_normalise_domain_lowercase() -> None:
    assert LicenseService._normalise_domain("https://ExAmPLE.COM") == "example.com"


def test_normalise_domain_handles_bare_domain() -> None:
    assert LicenseService._normalise_domain("example.com") == "example.com"
