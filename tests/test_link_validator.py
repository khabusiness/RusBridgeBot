from __future__ import annotations

from app.services.link_validator import validate_service_link


def test_valid_domain_link() -> None:
    result = validate_service_link("https://pay.openai.com/invoice/123", ["pay.openai.com"])
    assert result.is_valid
    assert result.normalized_url == "https://pay.openai.com/invoice/123"


def test_wrong_domain_is_rejected() -> None:
    result = validate_service_link("https://evil.com/pay", ["pay.openai.com"])
    assert not result.is_valid
    assert result.error_code == "domain"


def test_non_https_is_rejected() -> None:
    result = validate_service_link("http://pay.openai.com/invoice", ["pay.openai.com"])
    assert not result.is_valid
    assert result.error_code == "scheme"

