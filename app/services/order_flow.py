from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.config import Settings
from app.enums import OrderStatus
from app.products import Product
from app.repository import ActiveOrderExistsError, Repository, utcnow
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

    def _build_payment_link(self, order: dict[str, Any], product: Product) -> PaymentLink:
        return self.payment_service.create_payment_link(
            order_id=order["order_id"],
            inv_id=int(order["payment_inv_id"]),
            amount_rub=product.price_rub,
            description=f"{product.name} ({order['order_id']})",
        )

    def create_or_resume_order(
        self,
        *,
        tg_id: int,
        username: str | None,
        source_key: str | None,
        product_code: str,
    ) -> CreateOrderResult:
        product = self.products[product_code]
        try:
            order = self.repository.create_order(
                tg_id=tg_id,
                username=username,
                source_key=source_key,
                product_code=product.code,
                product_name=product.name,
                price_rub=product.price_rub,
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

        payment = self._build_payment_link(order=order, product=product)
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
