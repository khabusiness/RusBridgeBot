from __future__ import annotations

from datetime import date

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.bot.handlers import send_renew_reminder
from app.enums import OrderStatus
from app.repository import utcnow
from app.runtime import AppContainer
from app.state_machine import TransitionError


def build_scheduler(container: AppContainer, bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    async def expire_orders_job() -> None:
        now = utcnow()

        wait_pay_expired = container.repository.find_orders_for_wait_pay_timeout(
            now_dt=now,
            timeout_minutes=container.settings.wait_pay_timeout_minutes,
        )
        for order in wait_pay_expired:
            try:
                expired = container.repository.transition_order(
                    order_id=order["order_id"],
                    target_status=OrderStatus.EXPIRED.value,
                    fields={"error_code": "WAIT_PAY_TIMEOUT", "error_text": "Истёк таймаут оплаты"},
                )
            except TransitionError:
                continue
            await bot.send_message(
                chat_id=int(expired["tg_id"]),
                text=(
                    f"Заказ {expired['order_id']} истёк по таймауту оплаты.\n"
                    "Если актуально, начните оформление заново через /start."
                ),
            )
            await bot.send_message(
                chat_id=container.settings.admin_chat_id,
                text=f"ORDER EXPIRED (WAIT_PAY)\nOrder ID: {expired['order_id']}",
            )

        wait_link_expired = container.repository.find_orders_for_wait_service_link_timeout(
            now_dt=now,
            timeout_hours=container.settings.wait_service_link_timeout_hours,
        )
        for order in wait_link_expired:
            try:
                expired = container.repository.transition_order(
                    order_id=order["order_id"],
                    target_status=OrderStatus.EXPIRED.value,
                    fields={"error_code": "WAIT_LINK_TIMEOUT", "error_text": "Истёк таймаут ссылки"},
                )
            except TransitionError:
                continue
            await bot.send_message(
                chat_id=int(expired["tg_id"]),
                text=(
                    f"Заказ {expired['order_id']} истёк: не получили ссылку вовремя.\n"
                    "Можно начать заново через /start."
                ),
            )
            await bot.send_message(
                chat_id=container.settings.admin_chat_id,
                text=f"ORDER EXPIRED (WAIT_SERVICE_LINK)\nOrder ID: {expired['order_id']}",
            )

    async def reminders_job() -> None:
        today = date.today()
        due = container.repository.list_subscriptions_due(today)
        for row in due:
            end_date = date.fromisoformat(row["end_date"])
            days_left = (end_date - today).days

            if days_left == 3 and int(row["remind_3_sent"]) == 0:
                await send_renew_reminder(
                    container=container,
                    bot=bot,
                    tg_id=int(row["tg_id"]),
                    product_code=row["product_code"],
                    days_left=days_left,
                )
                container.repository.mark_subscription_reminder_sent(int(row["id"]), days_left=3)

            if days_left <= 0 and int(row["remind_0_sent"]) == 0:
                await send_renew_reminder(
                    container=container,
                    bot=bot,
                    tg_id=int(row["tg_id"]),
                    product_code=row["product_code"],
                    days_left=days_left,
                )
                container.repository.mark_subscription_reminder_sent(int(row["id"]), days_left=0)

    scheduler.add_job(expire_orders_job, "interval", minutes=container.settings.timeout_scan_minutes)
    scheduler.add_job(reminders_job, "interval", hours=container.settings.reminders_interval_hours)
    return scheduler
