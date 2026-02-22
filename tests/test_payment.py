from __future__ import annotations

import hashlib

from app.config import Settings
from app.services.payment import RobokassaService


def _settings(test_mode: bool) -> Settings:
    return Settings(
        bot_token="token",
        admin_chat_id=-100123,
        owner_chat_id=None,
        database_path=":memory:",
        products_file="data/products.json",
        payment_test_mode=test_mode,
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


def test_create_payment_link_uses_stub_in_test_mode() -> None:
    service = RobokassaService(_settings(test_mode=True))
    link = service.create_payment_link(
        order_id="RB-1",
        inv_id=10,
        amount_rub=2990,
        description="test",
    )
    assert link.provider_mode == "stub"
    assert link.pay_url.startswith("https://khabusiness.github.io/rusbridge-site/success.html")


def test_verify_result_signature_true_for_valid_payload() -> None:
    service = RobokassaService(_settings(test_mode=False))
    payload_without_signature = {
        "OutSum": "2990.00",
        "InvId": "10",
        "Shp_order_id": "RB-10",
    }
    base = "2990.00:10:pass2:Shp_order_id=RB-10"
    signature = hashlib.md5(base.encode("utf-8")).hexdigest()  # noqa: S324 - compatibility test
    payload = dict(payload_without_signature)
    payload["SignatureValue"] = signature

    assert service.verify_result_signature(payload)


def test_verify_result_signature_false_for_bad_signature() -> None:
    service = RobokassaService(_settings(test_mode=False))
    payload = {
        "OutSum": "2990.00",
        "InvId": "10",
        "Shp_order_id": "RB-10",
        "SignatureValue": "deadbeef",
    }
    assert not service.verify_result_signature(payload)

