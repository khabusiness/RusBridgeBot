from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse


BLOCKED_SHORT_DOMAINS = {
    "bit.ly",
    "t.co",
    "tinyurl.com",
    "goo.gl",
    "vk.cc",
}


@dataclass(slots=True)
class LinkValidationResult:
    is_valid: bool
    normalized_url: str | None
    error_code: str | None = None
    error_text: str | None = None


def validate_service_link(raw_text: str, allowed_domains: list[str]) -> LinkValidationResult:
    candidate = raw_text.strip()
    if not candidate:
        return LinkValidationResult(
            is_valid=False,
            normalized_url=None,
            error_code="empty",
            error_text="Пустое сообщение. Нужна ссылка.",
        )

    if " " in candidate:
        return LinkValidationResult(
            is_valid=False,
            normalized_url=None,
            error_code="not_single_url",
            error_text="Нужна одна ссылка без дополнительных слов.",
        )

    parsed = urlparse(candidate)
    if parsed.scheme.lower() != "https":
        return LinkValidationResult(
            is_valid=False,
            normalized_url=None,
            error_code="scheme",
            error_text="Ссылка должна начинаться с https://",
        )

    host = (parsed.hostname or "").lower().strip(".")
    if not host:
        return LinkValidationResult(
            is_valid=False,
            normalized_url=None,
            error_code="host",
            error_text="Не удалось определить домен в ссылке.",
        )

    if host in BLOCKED_SHORT_DOMAINS:
        return LinkValidationResult(
            is_valid=False,
            normalized_url=None,
            error_code="shortener",
            error_text="Сокращённые ссылки не принимаются.",
        )

    normalized = f"https://{host}{parsed.path or ''}"
    if parsed.query:
        normalized += f"?{parsed.query}"

    if allowed_domains:
        good = any(host == domain or host.endswith(f".{domain}") for domain in allowed_domains)
        if not good:
            domains = ", ".join(allowed_domains)
            return LinkValidationResult(
                is_valid=False,
                normalized_url=None,
                error_code="domain",
                error_text=f"Ожидается домен: {domains}",
            )

    return LinkValidationResult(is_valid=True, normalized_url=normalized)

