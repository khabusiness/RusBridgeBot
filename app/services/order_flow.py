from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.enums import OrderStatus
from app.products import Product
from app.repository import (
    ActiveOrderExistsError,
    Repository,
    UserHasOpenOrderError,
    utcnow,
)
from app.services.payment import PaymentLink, RobokassaService


@dataclass(slots=True)
class CreateOrderResult:
    order: dict[str, Any]
    payment: PaymentLink
    reused_active_order: bool


@dataclass(slots=True)
class PaymentWebhookResult:
    order: dict[str, Any] | None
    updated: bool
    reason: str


@dataclass(slots=True)
class DailyOrderLimitExceededError(Exception):
    tg_id: int
    limit: int
    created_today: int

    def __str__(self) -> str:
        return (
            f"Daily order limit exceeded for tg_id={self.tg_id}: "
            f"{self.created_today}/{self.limit}"
        )


class OrderFlowService:
    def __init__(
        self,
        repository: Repository,
        products: dict[str, Product],
        payment_service: RobokassaService,
        settings: Settings,
    ):
        self.repository = repository
        self.products = products
        self.payment_service = payment_service
        self.settings = settings

    def get_product(self, product_code: str) -> Product | None:
        return self.products.get(product_code)

    def _build_payment_link(self, order: dict[str, Any]) -> PaymentLink:
        return self.payment_service.create_payment_link(
            order_id=order["order_id"],
            inv_id=int(order["payment_inv_id"]),
            amount_rub=int(order["price_rub"]),
            description=f"{order['product_name']} ({order['order_id']})",
        )

    def get_payment_link_for_order(self, order: dict[str, Any]) -> PaymentLink:
        payment = self._build_payment_link(order=order)
        self.repository.update_payment_fields(order["order_id"], out_sum=payment.out_sum)
        return payment

    def create_or_resume_order(
        self,
        *,
        tg_id: int,
        username: str | None,
        source_key: str | None,
        product_code: str,
        custom_price_rub: int | None = None,
        custom_product_name: str | None = None,
    ) -> CreateOrderResult:
        product = self.products[product_code]
        target_price_rub = custom_price_rub if custom_price_rub is not None else product.price_rub
        target_product_name = custom_product_name or product.name
        active_any = self.repository.find_active_order_any(tg_id=tg_id)
        if active_any is not None:
            if active_any["product_code"] != product_code:
                raise UserHasOpenOrderError(
                    tg_id=tg_id,
                    existing_order_id=active_any["order_id"],
                    existing_product_code=active_any["product_code"],
                    existing_status=active_any["status"],
                )
            if active_any["status"] == OrderStatus.NEW.value:
                active_any = self.repository.transition_order(
                    order_id=active_any["order_id"],
                    target_status=OrderStatus.WAIT_PAY.value,
                )
            payment = self._build_payment_link(order=active_any)
            self.repository.update_payment_fields(active_any["order_id"], out_sum=payment.out_sum)
            return CreateOrderResult(order=active_any, payment=payment, reused_active_order=True)

        if not self.settings.test_id and self.settings.daily_order_limit > 0:
            now_dt = utcnow()
            day_start = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            created_today = self.repository.count_orders_created_between(
                tg_id=tg_id,
                start_iso=day_start.isoformat(),
                end_iso=day_end.isoformat(),
            )
            if created_today >= self.settings.daily_order_limit:
                raise DailyOrderLimitExceededError(
                    tg_id=tg_id,
                    limit=self.settings.daily_order_limit,
                    created_today=created_today,
                )
        try:
            order = self.repository.create_order(
                tg_id=tg_id,
                username=username,
                source_key=source_key,
                product_code=product.code,
                product_name=target_product_name,
                price_rub=target_price_rub,
                wait_pay_timeout_minutes=self.settings.wait_pay_timeout_minutes,
            )
            order = self.repository.transition_order(
                order_id=order["order_id"],
                target_status=OrderStatus.WAIT_PAY.value,
            )
            reused = False
        except ActiveOrderExistsError as exc:
            existing = self.repository.get_order(exc.existing_order_id or "")
            if existing is None:
                raise
            if existing["status"] == OrderStatus.NEW.value:
                existing = self.repository.transition_order(
                    order_id=existing["order_id"],
                    target_status=OrderStatus.WAIT_PAY.value,
                )
            order = existing
            reused = True

        payment = self._build_payment_link(order=order)
        self.repository.update_payment_fields(order["order_id"], out_sum=payment.out_sum)
        return CreateOrderResult(order=order, payment=payment, reused_active_order=reused)

    def handle_successful_payment_webhook(
        self,
        *,
        inv_id: int,
        out_sum: str,
        payment_status_text: str,
    ) -> PaymentWebhookResult:
        order = self.repository.get_order_by_payment_inv_id(inv_id)
        if order is None:
            return PaymentWebhookResult(order=None, updated=False, reason="order_not_found")

        status = order["status"]
        already_paid_chain = {
            OrderStatus.PAID.value,
            OrderStatus.WAIT_SERVICE_LINK.value,
            OrderStatus.READY_FOR_OPERATOR.value,
            OrderStatus.IN_PROGRESS.value,
            OrderStatus.DONE.value,
            OrderStatus.WAIT_CLIENT_CONFIRM.value,
            OrderStatus.CLIENT_CONFIRMED.value,
        }
        if status in already_paid_chain:
            return PaymentWebhookResult(order=order, updated=False, reason="already_processed")

        if status != OrderStatus.WAIT_PAY.value:
            return PaymentWebhookResult(order=order, updated=False, reason=f"unexpected_status:{status}")

        paid = self.repository.transition_order(
            order_id=order["order_id"],
            target_status=OrderStatus.PAID.value,
            fields={"paid_at": utcnow().isoformat()},
        )
        self.repository.update_payment_fields(
            order_id=order["order_id"],
            out_sum=out_sum,
            payment_status_text=payment_status_text,
        )
        wait_link = self.repository.transition_order(
            order_id=order["order_id"],
            target_status=OrderStatus.WAIT_SERVICE_LINK.value,
        )
        return PaymentWebhookResult(order=wait_link or paid, updated=True, reason="ok")

    def set_service_link(self, *, order_id: str, link: str) -> dict[str, Any]:
        return self.repository.set_service_link_ready(order_id=order_id, service_link=link)

    def mark_client_confirmed(self, order: dict[str, Any]) -> dict[str, Any]:
        confirmed = self.repository.mark_order_client_confirmed(order["order_id"])
        product = self.products[order["product_code"]]
        start = date.today()
        end = start + timedelta(days=product.duration_days)
        self.repository.upsert_subscription(
            tg_id=int(order["tg_id"]),
            product_code=product.code,
            start_date_iso=start.isoformat(),
            end_date_iso=end.isoformat(),
            last_order_id=order["order_id"],
        )
        return confirmed
