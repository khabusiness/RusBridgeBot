from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    db_path = tmp_path / "test.sqlite3"
    return Settings(
        bot_token="token",
        admin_chat_id=-100123,
        owner_chat_id=1,
        database_path=str(db_path),
        products_file=str(tmp_path / "products.json"),
        payment_test_mode=True,
        mock_payment_success_url="https://khabusiness.github.io/rusbridge-site/success.html",
        mock_payment_fail_url="https://khabusiness.github.io/rusbridge-site/fail.html",
        robokassa_merchant_login="merchant",
        robokassa_password1="pass1",
        robokassa_password2="pass2",
        robokassa_hash_algo="md5",
        robokassa_result_url="https://example.com/result",
        robokassa_success_url="https://example.com/success",
        robokassa_fail_url="https://example.com/fail",
        robokassa_is_test=False,
        web_host="127.0.0.1",
        web_port=8080,
        wait_pay_timeout_minutes=60,
        wait_service_link_timeout_hours=12,
        reminders_interval_hours=6,
        timeout_scan_minutes=10,
    )

