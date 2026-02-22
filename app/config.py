from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "y"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    return int(value.strip())


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip("'").strip('"')
    return result


def _read_first(
    env: dict[str, str],
    *keys: str,
    required: bool = False,
    default: str | None = None,
) -> str | None:
    for key in keys:
        if key in os.environ:
            return os.environ[key]
        if key in env:
            return env[key]
    if required and default is None:
        joined = ", ".join(keys)
        raise ValueError(f"Required setting is missing. Expected one of: {joined}")
    return default


@dataclass(slots=True)
class Settings:
    bot_token: str
    admin_chat_id: int
    owner_chat_id: int | None
    database_path: str
    products_file: str
    payment_test_mode: bool
    mock_payment_success_url: str
    mock_payment_fail_url: str
    robokassa_merchant_login: str
    robokassa_password1: str
    robokassa_password2: str
    robokassa_hash_algo: str
    robokassa_result_url: str
    robokassa_success_url: str
    robokassa_fail_url: str
    robokassa_is_test: bool
    web_host: str
    web_port: int
    wait_pay_timeout_minutes: int
    wait_service_link_timeout_hours: int
    reminders_interval_hours: int
    timeout_scan_minutes: int


def load_settings(env_file: str = ".env") -> Settings:
    env = _read_dotenv(Path(env_file))

    bot_token = _read_first(
        env,
        "RUSBRIDGEBOT_TOKEN",
        required=True,
    )
    admin_chat_id_raw = _read_first(
        env,
        "RUSBRIDGECANNAL_CHAT_ID",
        "RUSBRIDGECANAL_CHAT_ID",
        required=True,
    )
    owner_chat_id_raw = _read_first(env, "USER_CHAT_ID", default=None)

    settings = Settings(
        bot_token=bot_token or "",
        admin_chat_id=int(admin_chat_id_raw or "0"),
        owner_chat_id=int(owner_chat_id_raw) if owner_chat_id_raw else None,
        database_path=_read_first(env, "SQLITE_DB_PATH", default="rusbridge.db") or "rusbridge.db",
        products_file=_read_first(env, "PRODUCTS_FILE", default="data/products.json") or "data/products.json",
        payment_test_mode=_parse_bool(_read_first(env, "PAYMENT_TEST_MODE", default="true"), True),
        mock_payment_success_url=_read_first(
            env,
            "MOCK_PAYMENT_SUCCESS_URL",
            default="https://khabusiness.github.io/rusbridge-site/success.html",
        )
        or "https://khabusiness.github.io/rusbridge-site/success.html",
        mock_payment_fail_url=_read_first(
            env,
            "MOCK_PAYMENT_FAIL_URL",
            default="https://khabusiness.github.io/rusbridge-site/fail.html",
        )
        or "https://khabusiness.github.io/rusbridge-site/fail.html",
        robokassa_merchant_login=_read_first(env, "ID_MAGAZIN_ROBOCASSA", required=True) or "",
        robokassa_password1=_read_first(env, "PASSWORD_1", required=True) or "",
        robokassa_password2=_read_first(env, "PASSWORD_2", required=True) or "",
        robokassa_hash_algo=(
            _read_first(env, "ROBOCASSA_HASH_ALGO", default="md5") or "md5"
        ).lower(),
        robokassa_result_url=_read_first(env, "RESULT_URL", required=True) or "",
        robokassa_success_url=_read_first(env, "SUCCESS_URL", required=True) or "",
        robokassa_fail_url=_read_first(env, "FAIL_URL", required=True) or "",
        robokassa_is_test=_parse_bool(_read_first(env, "ROBOCASSA_IS_TEST", default="false"), False),
        web_host=_read_first(env, "WEB_HOST", default="0.0.0.0") or "0.0.0.0",
        web_port=_parse_int(_read_first(env, "PORT", "WEB_PORT", default="8080"), 8080),
        wait_pay_timeout_minutes=_parse_int(
            _read_first(env, "WAIT_PAY_TIMEOUT_MINUTES", default="60"),
            60,
        ),
        wait_service_link_timeout_hours=_parse_int(
            _read_first(env, "WAIT_SERVICE_LINK_TIMEOUT_HOURS", default="12"),
            12,
        ),
        reminders_interval_hours=_parse_int(
            _read_first(env, "REMINDERS_INTERVAL_HOURS", default="6"),
            6,
        ),
        timeout_scan_minutes=_parse_int(
            _read_first(env, "TIMEOUT_SCAN_MINUTES", default="10"),
            10,
        ),
    )
    return settings

