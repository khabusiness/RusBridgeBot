from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.db import init_db
from app.enums import OrderStatus
from app.products import load_products
from app.repository import ActiveOrderExistsError, Repository, UserHasOpenOrderError
from app.services.order_flow import DailyOrderLimitExceededError, OrderFlowService
from app.services.payment import RobokassaService


def _write_products(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "code": "gpt_plus_1m",
                    "name": "GPT Plus 1m",
                    "price_rub": 2990,
                    "duration_days": 30,
                    "requirements": [],
                    "service_link_prompt": "send link",
                    "instruction_template": "template",
                    "allowed_domains": ["pay.openai.com"],
                },
                {
                    "code": "openrouter",
                    "name": "OpenRouter",
                    "price_rub": 0,
                    "duration_days": 30,
                    "requirements": [],
                    "service_link_prompt": "send link",
                    "instruction_template": "template",
                    "allowed_domains": ["openrouter.ai"],
                }
            ]
        ),
        encoding="utf-8",
    )


def test_one_active_order_per_service(settings, tmp_path: Path) -> None:
    _write_products(Path(settings.products_file))
    init_db(settings.database_path)
    repo = Repository(settings.database_path)

    first = repo.create_order(
        tg_id=10,
        username="u",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
        product_name="GPT Plus 1m",
        price_rub=2990,
        wait_pay_timeout_minutes=60,
    )
    repo.transition_order(first["order_id"], OrderStatus.WAIT_PAY.value)

    with pytest.raises(ActiveOrderExistsError):
        repo.create_order(
            tg_id=10,
            username="u",
            source_key="gpt_plus_1m",
            product_code="gpt_plus_1m",
            product_name="GPT Plus 1m",
            price_rub=2990,
            wait_pay_timeout_minutes=60,
        )

    repo.transition_order(first["order_id"], OrderStatus.CANCELLED.value)
    second = repo.create_order(
        tg_id=10,
        username="u",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
        product_name="GPT Plus 1m",
        price_rub=2990,
        wait_pay_timeout_minutes=60,
    )
    assert second["order_id"] != first["order_id"]


def test_payment_webhook_is_idempotent(settings, tmp_path: Path) -> None:
    _write_products(Path(settings.products_file))
    init_db(settings.database_path)
    repo = Repository(settings.database_path)
    products = load_products(settings.products_file)
    payment = RobokassaService(settings)
    flow = OrderFlowService(repo, products, payment, settings)

    created = flow.create_or_resume_order(
        tg_id=11,
        username="client",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
    )
    order = created.order
    first = flow.handle_successful_payment_webhook(
        inv_id=int(order["payment_inv_id"]),
        out_sum="2990.00",
        payment_status_text="ok",
    )
    assert first.updated
    assert first.order is not None
    assert first.order["status"] == OrderStatus.WAIT_SERVICE_LINK.value

    second = flow.handle_successful_payment_webhook(
        inv_id=int(order["payment_inv_id"]),
        out_sum="2990.00",
        payment_status_text="ok",
    )
    assert not second.updated
    assert second.reason == "already_processed"


def test_create_order_with_custom_price(settings, tmp_path: Path) -> None:
    _write_products(Path(settings.products_file))
    init_db(settings.database_path)
    repo = Repository(settings.database_path)
    products = load_products(settings.products_file)
    payment = RobokassaService(settings)
    flow = OrderFlowService(repo, products, payment, settings)

    created = flow.create_or_resume_order(
        tg_id=12,
        username="client",
        source_key="openrouter:25usd",
        product_code="openrouter",
        custom_price_rub=2600,
        custom_product_name="OpenRouter (25 USD)",
    )

    assert created.order["price_rub"] == 2600
    assert created.order["product_name"] == "OpenRouter (25 USD)"
    assert created.payment.out_sum == "2600.00"


def test_one_active_order_per_user_across_products(settings, tmp_path: Path) -> None:
    _write_products(Path(settings.products_file))
    init_db(settings.database_path)
    repo = Repository(settings.database_path)
    products = load_products(settings.products_file)
    payment = RobokassaService(settings)
    flow = OrderFlowService(repo, products, payment, settings)

    first = flow.create_or_resume_order(
        tg_id=13,
        username="client",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
    )
    assert first.order["status"] == OrderStatus.WAIT_PAY.value

    with pytest.raises(UserHasOpenOrderError):
        flow.create_or_resume_order(
            tg_id=13,
            username="client",
            source_key="openrouter",
            product_code="openrouter",
        )


def test_daily_limit_blocks_new_orders_when_test_id_disabled(settings, tmp_path: Path) -> None:
    settings.daily_order_limit = 2
    settings.test_id = False
    _write_products(Path(settings.products_file))
    init_db(settings.database_path)
    repo = Repository(settings.database_path)
    products = load_products(settings.products_file)
    payment = RobokassaService(settings)
    flow = OrderFlowService(repo, products, payment, settings)

    first = flow.create_or_resume_order(
        tg_id=14,
        username="client",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
    )
    repo.transition_order(first.order["order_id"], OrderStatus.CANCELLED.value)

    second = flow.create_or_resume_order(
        tg_id=14,
        username="client",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
    )
    repo.transition_order(second.order["order_id"], OrderStatus.CANCELLED.value)

    with pytest.raises(DailyOrderLimitExceededError):
        flow.create_or_resume_order(
            tg_id=14,
            username="client",
            source_key="gpt_plus_1m",
            product_code="gpt_plus_1m",
        )


def test_daily_limit_is_ignored_when_test_id_enabled(settings, tmp_path: Path) -> None:
    settings.daily_order_limit = 1
    settings.test_id = True
    _write_products(Path(settings.products_file))
    init_db(settings.database_path)
    repo = Repository(settings.database_path)
    products = load_products(settings.products_file)
    payment = RobokassaService(settings)
    flow = OrderFlowService(repo, products, payment, settings)

    first = flow.create_or_resume_order(
        tg_id=15,
        username="client",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
    )
    repo.transition_order(first.order["order_id"], OrderStatus.CANCELLED.value)

    second = flow.create_or_resume_order(
        tg_id=15,
        username="client",
        source_key="gpt_plus_1m",
        product_code="gpt_plus_1m",
    )
    assert second.order["order_id"] != first.order["order_id"]


def test_block_and_unblock_user(settings, tmp_path: Path) -> None:
    _write_products(Path(settings.products_file))
    init_db(settings.database_path)
    repo = Repository(settings.database_path)

    assert not repo.is_user_blocked(16)
    repo.block_user(tg_id=16, blocked_by=9001, reason="spam")
    block = repo.get_user_block(16)
    assert block is not None
    assert block["reason"] == "spam"
    assert repo.is_user_blocked(16)
    repo.unblock_user(16)
    assert not repo.is_user_blocked(16)
