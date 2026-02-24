from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, LinkPreviewOptions, Message

from app.bot.keyboards import (
    admin_order_keyboard,
    client_confirm_keyboard,
    confirm_product_keyboard,
    payment_keyboard,
    payment_retry_keyboard,
    payment_test_confirm_keyboard,
    payment_test_fail_keyboard,
    provider_picker_keyboard,
    product_picker_keyboard,
    renew_keyboard,
)
from app.bot.texts import (
    admin_link_received,
    admin_new_lead,
    admin_paid,
    ask_service_link_text,
    invalid_service_link_text,
    order_wait_pay_text,
    product_confirmation_text,
)
from app.enums import OrderStatus
from app.products import PROVIDER_TITLES
from app.runtime import AppContainer
from app.services.link_validator import validate_service_link


PRODUCT_ALIASES = {
    "nano_basic_1m": "nano_banana",
    "nano_banana_basic_1m": "nano_banana",
    "nano_banana_pro_1m": "nano_banana",
    "nano_banana_max_1m": "nano_banana",
}
OPENROUTER_CODE = "openrouter"
NANO_BANANA_CODE = "nano_banana"
VARIABLE_PRICE_MARKUP = 1.3
VARIABLE_PRICE_RUB_RATE = 80
VARIABLE_PRICE_PRODUCT_CODES = {OPENROUTER_CODE, NANO_BANANA_CODE}
NANO_GUIDE_PATH = Path("data/Nano.jpg")
DEFAULT_POST_PAYMENT_GUIDE_PATH = Path("data/GPT.jpg")
POST_PAYMENT_PROVIDER_GUIDE_BY_PROVIDER: dict[str, Path] = {
    "gpt": Path("data/GPT.jpg"),
    "claude": Path("data/Cloude.jpg"),
    "cursor": Path("data/Cursore.jpg"),
    "copilot": Path("data/Copilot.jpg"),
}


def _order_status_hint(status: str) -> str:
    hints = {
        OrderStatus.WAIT_PAY.value: "ждём подтверждение оплаты",
        OrderStatus.WAIT_SERVICE_LINK.value: "пришлите ссылку оплаты сервиса",
        OrderStatus.READY_FOR_OPERATOR.value: "заказ уже в очереди оператора",
        OrderStatus.IN_PROGRESS.value: "оператор уже работает над заказом",
        OrderStatus.WAIT_CLIENT_CONFIRM.value: "осталось подтвердить, что всё активно",
    }
    return hints.get(status, status)


def build_router(container: AppContainer, bot: Bot) -> Router:
    router = Router()
    pending_variable_price_input: dict[int, str] = {}

    def _variable_price_rub(usd_amount: int) -> int:
        return int(usd_amount * VARIABLE_PRICE_MARKUP * VARIABLE_PRICE_RUB_RATE)

    async def ask_variable_amount(message: Message, product_code: str) -> None:
        pending_variable_price_input[message.from_user.id] = product_code
        if product_code == NANO_BANANA_CODE:
            nano_hint = (
                "Для Nano Banana:\n"
                "Зайдите на любой из сайтов:\n"
                "https://nanobanana.im/\n"
                "https://nanobanapro.com/\n"
                "https://www.nano-banana.ai/\n"
                "https://nano-banana.io/\n"
                "или аналогичный сайт Nano Banana.\n\n"
                "Выберите подписку или разовый пакет, затем введите сумму в долларах."
            )
            if NANO_GUIDE_PATH.exists():
                await message.answer_photo(photo=FSInputFile(str(NANO_GUIDE_PATH)), caption=nano_hint)
            else:
                await message.answer(nano_hint)
        await message.answer(
            "Сколько долларов положить?\n"
            "Введите целое число в USD (например: 10)."
        )

    async def send_provider_menu(message: Message, *, text: str = "Что оформить?") -> None:
        await message.answer(
            text,
            reply_markup=provider_picker_keyboard(container.products),
        )

    async def send_admin(text: str, *, reply_markup: Any | None = None) -> None:
        await bot.send_message(
            chat_id=container.settings.admin_chat_id,
            text=text,
            reply_markup=reply_markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    async def send_wait_pay_resume(message: Message, order: dict[str, Any], *, reason: str | None = None) -> None:
        product = container.products[order["product_code"]]
        payment = container.order_flow.get_payment_link_for_order(order)
        if reason:
            await message.answer(reason)
        await message.answer(
            order_wait_pay_text(
                product,
                order["order_id"],
                container.settings.payment_test_mode,
                price_rub=int(order["price_rub"]),
            ),
            reply_markup=payment_keyboard(payment.pay_url),
        )
        await message.answer(
            "Если оплата не прошла, можно повторить или отменить заказ:",
            reply_markup=payment_retry_keyboard(payment.pay_url, order["order_id"]),
        )

    @router.message(CommandStart())
    async def handle_start(message: Message) -> None:
        payload = None
        if message.text and " " in message.text:
            payload = message.text.split(" ", 1)[1].strip()
        normalized_payload = PRODUCT_ALIASES.get(payload, payload) if payload else None

        container.repository.upsert_user(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            source_key=payload,
        )

        if payload and payload.startswith("payfail_"):
            order_id = payload.removeprefix("payfail_")
            order = container.repository.get_order(order_id)
            if order is None or int(order["tg_id"]) != message.from_user.id:
                await message.answer("Заказ не найден. Используйте /start для нового оформления.")
                return
            if order["status"] == OrderStatus.WAIT_PAY.value:
                await send_wait_pay_resume(
                    message,
                    order,
                    reason="Оплата не прошла или была отменена. Вы можете попробовать снова.",
                )
                return
            await message.answer(
                f"Order ID: {order['order_id']}\n"
                f"Статус: {order['status']}\n"
                f"Комментарий: {_order_status_hint(order['status'])}"
            )
            return

        if normalized_payload and normalized_payload in container.products:
            product = container.products[normalized_payload]
            if product.code in VARIABLE_PRICE_PRODUCT_CODES:
                await ask_variable_amount(message, product.code)
                return
            await message.answer(
                product_confirmation_text(product),
                reply_markup=confirm_product_keyboard(product.code),
            )
            return

        if payload and normalized_payload not in container.products:
            await message.answer(
                "Ключ оффера не найден. Выберите подписку из списка:",
                reply_markup=provider_picker_keyboard(container.products),
            )
            return

        wait_pay_orders = container.repository.list_orders_by_user_and_statuses(
            tg_id=message.from_user.id,
            statuses=[OrderStatus.WAIT_PAY.value],
        )
        if wait_pay_orders:
            await send_wait_pay_resume(
                message,
                wait_pay_orders[0],
                reason="У вас есть незавершённая оплата. Продолжим её?",
            )
            return

        await message.answer(
            "Что оформить?",
            reply_markup=provider_picker_keyboard(container.products),
        )

    @router.message(Command("help"))
    async def handle_help(message: Message) -> None:
        await message.answer(
            "Я помогу оформить подписку.\n"
            "1) Выберите продукт\n"
            "2) Оплатите счёт\n"
            "3) Пришлите ссылку оплаты сервиса\n\n"
            "Команды:\n"
            "/status [order_id] - статус заказа\n"
            "/cancel <order_id> - отмена заказа (если доступно)\n"
            "/operator - позвать оператора\n"
            "Или напишите: МОД: ваш вопрос"
        )

    @router.message(Command("operator"))
    async def handle_operator(message: Message) -> None:
        await message.answer("Оператору отправлен запрос. Ожидайте ответ в этом чате.")
        await send_admin(
            "CLIENT NEEDS OPERATOR\n"
            f"Пользователь: @{message.from_user.username or 'без_username'} "
            f"(id: {message.from_user.id})"
        )

    @router.message(Command("msg"))
    async def admin_send_message(message: Message) -> None:
        if message.chat.id != container.settings.admin_chat_id:
            await message.answer("Команда доступна только в админ-чате.")
            return
        if not message.text:
            await message.answer("Формат: /msg <tg_id|order_id> <текст>")
            return

        parts = message.text.split(" ", 2)
        if len(parts) < 3 or not parts[1].strip() or not parts[2].strip():
            await message.answer("Формат: /msg <tg_id|order_id> <текст>")
            return

        target = parts[1].strip()
        text_to_client = parts[2].strip()
        target_tg_id: int | None = None

        if target.upper().startswith("RB-"):
            order = container.repository.get_order(target)
            if order is None:
                await message.answer("Order ID не найден.")
                return
            target_tg_id = int(order["tg_id"])
        else:
            try:
                target_tg_id = int(target)
            except ValueError:
                await message.answer("Укажите корректный tg_id или Order ID (RB-...).")
                return

        await bot.send_message(
            chat_id=target_tg_id,
            text="Сообщение от оператора:\n" + text_to_client,
        )
        await message.answer(f"Отправлено пользователю {target_tg_id}.")

    @router.callback_query(F.data.startswith("product:"))
    async def choose_product(callback: CallbackQuery) -> None:
        product_code = callback.data.split(":", 1)[1]
        product_code = PRODUCT_ALIASES.get(product_code, product_code)
        product = container.products.get(product_code)
        if not product:
            await callback.answer("Продукт не найден", show_alert=True)
            return

        if product.code in VARIABLE_PRICE_PRODUCT_CODES:
            if callback.message is None:
                await callback.answer("Сообщение недоступно", show_alert=True)
                return
            await ask_variable_amount(callback.message, product.code)
            await callback.answer()
            return

        await callback.message.answer(
            product_confirmation_text(product),
            reply_markup=confirm_product_keyboard(product.code),
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("provider:"))
    async def choose_provider(callback: CallbackQuery) -> None:
        provider = callback.data.split(":", 1)[1]
        has_products = any(
            not product.hidden and product.provider == provider for product in container.products.values()
        )
        if not has_products:
            await callback.answer("В этой категории пока нет тарифов", show_alert=True)
            return

        provider_title = PROVIDER_TITLES.get(provider, provider.title())
        await callback.message.answer(
            f"Выберите подписку: {provider_title}",
            reply_markup=product_picker_keyboard(container.products, provider=provider, include_back=True),
        )
        await callback.answer()

    @router.callback_query(F.data == "providers")
    async def show_providers(callback: CallbackQuery) -> None:
        await callback.message.answer(
            "Что оформить?",
            reply_markup=provider_picker_keyboard(container.products),
        )
        await callback.answer()

    @router.callback_query(F.data == "choose_other")
    async def choose_other(callback: CallbackQuery) -> None:
        await callback.message.answer(
            "Выберите подписку:",
            reply_markup=provider_picker_keyboard(container.products),
        )
        await callback.answer()

    @router.callback_query(F.data == "ask_operator")
    async def ask_operator(callback: CallbackQuery) -> None:
        await callback.message.answer(
            "Оператору отправлен запрос. Ожидайте ответ в этом чате."
        )
        await send_admin(
            "CLIENT NEEDS OPERATOR\n"
            f"Пользователь: @{callback.from_user.username or 'без_username'} "
            f"(id: {callback.from_user.id})"
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("confirm:"))
    async def confirm_product(callback: CallbackQuery) -> None:
        product_code = callback.data.split(":", 1)[1]
        product_code = PRODUCT_ALIASES.get(product_code, product_code)
        product = container.products.get(product_code)
        if product is None:
            await callback.answer("Продукт не найден", show_alert=True)
            return
        if product.code in VARIABLE_PRICE_PRODUCT_CODES:
            if callback.message is None:
                await callback.answer("Сообщение недоступно", show_alert=True)
                return
            await ask_variable_amount(callback.message, product.code)
            await callback.answer()
            return

        container.repository.upsert_user(
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
            source_key=product_code,
        )

        result = container.order_flow.create_or_resume_order(
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
            source_key=product_code,
            product_code=product_code,
        )
        order = result.order

        if result.reused_active_order and order["status"] != OrderStatus.WAIT_PAY.value:
            await callback.message.answer(
                "У вас уже есть активный заказ по этому продукту.\n"
                f"Order ID: {order['order_id']}\n"
                f"Статус: {_order_status_hint(order['status'])}"
            )
            await callback.answer()
            return

        await callback.message.answer(
            order_wait_pay_text(
                product,
                order["order_id"],
                container.settings.payment_test_mode,
                price_rub=int(order["price_rub"]),
            ),
            reply_markup=payment_keyboard(result.payment.pay_url),
        )
        await callback.message.answer(
            f"Заказ {order['order_id']} отслеживается автоматически.\n"
            "Если нужно, проверьте вручную: /status " + order["order_id"]
        )
        await callback.message.answer(
            "Если хотите отменить до подтверждения оплаты: /cancel " + order["order_id"]
        )
        if container.settings.payment_test_mode:
            await callback.message.answer(
                "Тестовый шаг: подтвердите успешную оплату.",
                reply_markup=payment_test_confirm_keyboard(order["order_id"]),
            )
            await callback.message.answer(
                "Тестовый шаг: сценарий неуспешной оплаты.",
                reply_markup=payment_test_fail_keyboard(order["order_id"]),
            )

        if not result.reused_active_order:
            await send_admin(admin_new_lead(order, source_label=order.get("source_key") or "unknown"))
        await callback.answer()

    @router.message(Command("status"))
    async def status_command(message: Message) -> None:
        order_id = None
        if message.text and " " in message.text:
            order_id = message.text.split(" ", 1)[1].strip()

        if order_id:
            order = container.repository.get_order(order_id)
            if order is None or int(order["tg_id"]) != message.from_user.id:
                await message.answer("Заказ не найден.")
                return
        else:
            active = container.repository.list_orders_by_user_and_statuses(
                tg_id=message.from_user.id,
                statuses=[
                    OrderStatus.NEW.value,
                    OrderStatus.WAIT_PAY.value,
                    OrderStatus.PAID.value,
                    OrderStatus.WAIT_SERVICE_LINK.value,
                    OrderStatus.READY_FOR_OPERATOR.value,
                    OrderStatus.IN_PROGRESS.value,
                    OrderStatus.DONE.value,
                    OrderStatus.WAIT_CLIENT_CONFIRM.value,
                ],
            )
            if not active:
                await message.answer("Активных заказов нет.")
                return
            order = active[0]

        await message.answer(
            f"Order ID: {order['order_id']}\n"
            f"Статус: {order['status']}\n"
            f"Комментарий: {_order_status_hint(order['status'])}"
        )

    @router.message(Command("cancel"))
    async def cancel_command(message: Message) -> None:
        order_id = None
        if message.text and " " in message.text:
            order_id = message.text.split(" ", 1)[1].strip()
        if not order_id:
            await message.answer("Укажите order_id: /cancel RB-...")
            return

        order = container.repository.get_order(order_id)
        if order is None or int(order["tg_id"]) != message.from_user.id:
            await message.answer("Заказ не найден.")
            return

        try:
            cancelled = container.repository.transition_order(
                order_id=order_id,
                target_status=OrderStatus.CANCELLED.value,
            )
            await message.answer(f"Заказ {cancelled['order_id']} отменён.")
            await send_admin(f"ORDER CANCELLED\nOrder ID: {cancelled['order_id']}")
        except Exception:
            await message.answer("Заказ нельзя отменить на текущем статусе.")

    @router.callback_query(F.data.startswith("check:"))
    async def check_payment(callback: CallbackQuery) -> None:
        order_id = callback.data.split(":", 1)[1]
        order = container.repository.get_order(order_id)
        if order is None or int(order["tg_id"]) != callback.from_user.id:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if order["status"] == OrderStatus.WAIT_PAY.value:
            await callback.message.answer(
                "Платёж пока не подтверждён. Обновление приходит автоматически по webhook."
            )
        elif order["status"] in {
            OrderStatus.PAID.value,
            OrderStatus.WAIT_SERVICE_LINK.value,
            OrderStatus.READY_FOR_OPERATOR.value,
            OrderStatus.IN_PROGRESS.value,
            OrderStatus.WAIT_CLIENT_CONFIRM.value,
            OrderStatus.CLIENT_CONFIRMED.value,
        }:
            await callback.message.answer(f"Текущий статус заказа: {order['status']}")
        else:
            await callback.message.answer(f"Текущий статус заказа: {order['status']}")
        await callback.answer()

    @router.callback_query(F.data.startswith("test_paid:"))
    async def test_paid(callback: CallbackQuery) -> None:
        if not container.settings.payment_test_mode:
            await callback.answer("Кнопка доступна только в test mode", show_alert=True)
            return
        if callback.message is None:
            await callback.answer("Сообщение недоступно", show_alert=True)
            return
        order_id = callback.data.split(":", 1)[1]
        order = container.repository.get_order(order_id)
        if order is None or int(order["tg_id"]) != callback.from_user.id:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        result = container.order_flow.handle_successful_payment_webhook(
            inv_id=int(order["payment_inv_id"]),
            out_sum=str(order.get("payment_out_sum") or order["price_rub"]),
            payment_status_text="test_mode_manual_confirm",
        )
        if not result.updated or result.order is None:
            await callback.answer("Статус не изменился", show_alert=True)
            return
        await notify_payment_confirmed(container, bot, result.order)
        await callback.answer("Оплата подтверждена в тестовом режиме")

    @router.callback_query(F.data.startswith("test_fail:"))
    async def test_fail(callback: CallbackQuery) -> None:
        if not container.settings.payment_test_mode:
            await callback.answer("Кнопка доступна только в test mode", show_alert=True)
            return
        if callback.message is None:
            await callback.answer("Сообщение недоступно", show_alert=True)
            return
        order_id = callback.data.split(":", 1)[1]
        order = container.repository.get_order(order_id)
        if order is None or int(order["tg_id"]) != callback.from_user.id:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        if order["status"] != OrderStatus.WAIT_PAY.value:
            await callback.answer("Заказ уже не ждёт оплату", show_alert=True)
            return

        await send_wait_pay_resume(
            callback.message,
            order,
            reason="Оплата не прошла или была отменена. Вы можете попробовать снова.",
        )
        await callback.answer("Показал сценарий отказа оплаты")

    @router.callback_query(F.data.startswith("cancel:"))
    async def cancel_order(callback: CallbackQuery) -> None:
        order_id = callback.data.split(":", 1)[1]
        order = container.repository.get_order(order_id)
        if order is None or int(order["tg_id"]) != callback.from_user.id:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        try:
            cancelled = container.repository.transition_order(
                order_id=order_id,
                target_status=OrderStatus.CANCELLED.value,
            )
            await callback.message.answer(f"Заказ {cancelled['order_id']} отменён.")
            await send_admin(f"ORDER CANCELLED\nOrder ID: {cancelled['order_id']}")
        except Exception:
            await callback.message.answer("Заказ нельзя отменить на текущем статусе.")
        await callback.answer()

    @router.callback_query(F.data.startswith("client_ok:"))
    async def client_ok(callback: CallbackQuery) -> None:
        order_id = callback.data.split(":", 1)[1]
        order = container.repository.get_order(order_id)
        if order is None or int(order["tg_id"]) != callback.from_user.id:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        if order["status"] != OrderStatus.WAIT_CLIENT_CONFIRM.value:
            await callback.answer("Этот заказ уже закрыт.", show_alert=True)
            return

        updated = container.order_flow.mark_client_confirmed(order)
        product = container.products[updated["product_code"]]
        end_date = (date.today() + timedelta(days=product.duration_days)).isoformat()
        await callback.message.answer(
            f"Отлично, заказ закрыт ✅\n"
            f"Напомним о продлении за 3 дня и в день окончания.\n"
            f"Order ID: {updated['order_id']}"
        )
        await send_admin(
            "CLIENT CONFIRMED\n"
            f"Order ID: {updated['order_id']}\n"
            f"Продукт: {updated['product_name']}\n"
            f"Подписка активна до: {end_date}"
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("client_fail:"))
    async def client_fail(callback: CallbackQuery) -> None:
        order_id = callback.data.split(":", 1)[1]
        order = container.repository.get_order(order_id)
        if order is None or int(order["tg_id"]) != callback.from_user.id:
            await callback.answer("Заказ не найден", show_alert=True)
            return
        if order["status"] != OrderStatus.WAIT_CLIENT_CONFIRM.value:
            await callback.answer("Этот заказ уже закрыт.", show_alert=True)
            return

        errored = container.repository.mark_order_error(
            order_id=order_id,
            error_code="CLIENT_NOT_ACTIVE",
            error_text="Клиент сообщил: не активно",
        )
        await callback.message.answer("Понял, подключаю оператора. Поможем вручную.")
        await send_admin(
            "CLIENT REPORTED ISSUE\n"
            f"Order ID: {errored['order_id']}\n"
            f"Ошибка: {errored['error_text']}"
        )
        await callback.answer()

    @router.callback_query(F.data.startswith("renew:"))
    async def renew_order(callback: CallbackQuery) -> None:
        product_code = callback.data.split(":", 1)[1]
        product_code = PRODUCT_ALIASES.get(product_code, product_code)
        product = container.products.get(product_code)
        if product is None:
            await callback.answer("Продукт не найден", show_alert=True)
            return

        result = container.order_flow.create_or_resume_order(
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
            source_key=f"renew_{product_code}",
            product_code=product_code,
        )
        await callback.message.answer(
            order_wait_pay_text(
                product,
                result.order["order_id"],
                container.settings.payment_test_mode,
                price_rub=int(result.order["price_rub"]),
            ),
            reply_markup=payment_keyboard(result.payment.pay_url),
        )
        await callback.message.answer(
            f"Заказ {result.order['order_id']} отслеживается автоматически.\n"
            "Если нужно, проверьте вручную: /status " + result.order["order_id"]
        )
        await callback.message.answer(
            "Если хотите отменить до подтверждения оплаты: /cancel " + result.order["order_id"]
        )
        if container.settings.payment_test_mode:
            await callback.message.answer(
                "Тестовый шаг: подтвердите успешную оплату.",
                reply_markup=payment_test_confirm_keyboard(result.order["order_id"]),
            )
            await callback.message.answer(
                "Тестовый шаг: сценарий неуспешной оплаты.",
                reply_markup=payment_test_fail_keyboard(result.order["order_id"]),
            )
        if not result.reused_active_order:
            await send_admin(admin_new_lead(result.order, source_label=f"renew_{product_code}"))
        await callback.answer()

    @router.message(F.chat.type == "private")
    async def handle_private_text(message: Message) -> None:
        if not message.text:
            return
        text = message.text.strip()
        container.repository.upsert_user(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            source_key=None,
        )

        lower_text = text.lower()
        if lower_text.startswith("мод:") or lower_text.startswith("mod:"):
            question = text.split(":", 1)[1].strip()
            if not question:
                await message.answer("После МОД: напишите ваш вопрос оператору.")
                return

            active_orders = container.repository.list_orders_by_user_and_statuses(
                tg_id=message.from_user.id,
                statuses=[
                    OrderStatus.NEW.value,
                    OrderStatus.WAIT_PAY.value,
                    OrderStatus.PAID.value,
                    OrderStatus.WAIT_SERVICE_LINK.value,
                    OrderStatus.READY_FOR_OPERATOR.value,
                    OrderStatus.IN_PROGRESS.value,
                    OrderStatus.DONE.value,
                    OrderStatus.WAIT_CLIENT_CONFIRM.value,
                ],
            )
            order_context = ""
            if active_orders:
                order_context = (
                    f"\nOrder ID: {active_orders[0]['order_id']}"
                    f"\nСтатус: {active_orders[0]['status']}"
                )

            await send_admin(
                "CLIENT QUESTION\n"
                f"Пользователь: @{message.from_user.username or 'без_username'} (id: {message.from_user.id})"
                f"{order_context}\n"
                f"Сообщение: {question}"
            )
            await message.answer("Сообщение отправлено оператору. Ожидайте ответ в этом чате.")
            return

        pending_product_code = pending_variable_price_input.get(message.from_user.id)
        if pending_product_code:
            if not text.isdigit():
                await message.answer("Нужно ввести целое число в долларах. Пример: 10")
                return
            usd_amount = int(text)
            if usd_amount <= 0:
                await message.answer("Сумма должна быть больше нуля. Пример: 10")
                return

            pending_variable_price_input.pop(message.from_user.id, None)
            product = container.products.get(pending_product_code)
            if product is None:
                await message.answer("Продукт временно недоступен, попробуйте позже.")
                return

            price_rub = _variable_price_rub(usd_amount)
            result = container.order_flow.create_or_resume_order(
                tg_id=message.from_user.id,
                username=message.from_user.username,
                source_key=f"{pending_product_code}:{usd_amount}usd",
                product_code=pending_product_code,
                custom_price_rub=price_rub,
                custom_product_name=f"{product.name} ({usd_amount} USD)",
            )
            order = result.order
            if result.reused_active_order and order["status"] != OrderStatus.WAIT_PAY.value:
                await message.answer(
                    "У вас уже есть активный заказ по этому продукту.\n"
                    f"Order ID: {order['order_id']}\n"
                    f"Статус: {_order_status_hint(order['status'])}"
                )
                return

            await message.answer(
                order_wait_pay_text(
                    product,
                    order["order_id"],
                    container.settings.payment_test_mode,
                    price_rub=int(order["price_rub"]),
                ),
                reply_markup=payment_keyboard(result.payment.pay_url),
            )
            await message.answer(
                f"Заказ {order['order_id']} отслеживается автоматически.\n"
                "Если нужно, проверьте вручную: /status " + order["order_id"]
            )
            await message.answer(
                "Если хотите отменить до подтверждения оплаты: /cancel " + order["order_id"]
            )
            if container.settings.payment_test_mode:
                await message.answer(
                    "Тестовый шаг: подтвердите успешную оплату.",
                    reply_markup=payment_test_confirm_keyboard(order["order_id"]),
                )
                await message.answer(
                    "Тестовый шаг: сценарий неуспешной оплаты.",
                    reply_markup=payment_test_fail_keyboard(order["order_id"]),
                )
            if not result.reused_active_order:
                await send_admin(admin_new_lead(order, source_label=order.get("source_key") or "unknown"))
            return


        waiting = container.repository.list_orders_by_user_and_statuses(
            tg_id=message.from_user.id,
            statuses=[OrderStatus.WAIT_SERVICE_LINK.value],
        )
        if not waiting:
            await message.answer(
                "Чтобы начать оформление, используйте /start или ссылку оффера."
            )
            return

        target_order = waiting[0]
        raw = text
        if len(waiting) > 1 and " " in raw:
            first, possible_url = raw.split(" ", 1)
            maybe = container.repository.get_order(first.strip())
            if maybe and int(maybe["tg_id"]) == message.from_user.id:
                target_order = maybe
                raw = possible_url.strip()

        product = container.products[target_order["product_code"]]
        result = validate_service_link(raw, product.allowed_domains)
        if not result.is_valid:
            await message.answer(invalid_service_link_text(result.error_text or "неизвестно"))
            await send_admin(
                "INVALID SERVICE LINK\n"
                f"Order ID: {target_order['order_id']}\n"
                f"Причина: {result.error_text or 'unknown'}"
            )
            return

        try:
            updated = container.order_flow.set_service_link(
                order_id=target_order["order_id"],
                link=result.normalized_url or raw,
            )
        except Exception:
            await message.answer(
                "Ссылка получена, но статус заказа уже изменился. Напишите оператору."
            )
            return

        await message.answer(
            "Ссылка получена ✅\n"
            "Ожидайте подтверждения (обычно 5-30 минут)."
        )
        await send_admin(
            admin_link_received(updated),
            reply_markup=admin_order_keyboard(updated["order_id"]),
        )

    @router.callback_query(F.data.startswith("admin_"))
    async def admin_actions(callback: CallbackQuery) -> None:
        if callback.message is None or callback.message.chat.id != container.settings.admin_chat_id:
            await callback.answer("Доступно только в админ-чате", show_alert=True)
            return

        action, order_id = callback.data.split(":", 1)
        order = container.repository.get_order(order_id)
        if order is None:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        admin_id = callback.from_user.id
        admin_username = callback.from_user.username

        try:
            if action == "admin_claim":
                updated = container.repository.claim_order(order_id, admin_id, admin_username)
                container.repository.log_admin_action(order_id, admin_id, admin_username, "CLAIM")
                await callback.message.answer(
                    f"CLAIM: {updated['order_id']} -> оператор @{admin_username or admin_id}"
                )

            elif action == "admin_progress":
                if order.get("operator_id") and int(order["operator_id"]) != admin_id:
                    await callback.answer("Заказ занят другим оператором", show_alert=True)
                    return
                if not order.get("operator_id"):
                    container.repository.claim_order(order_id, admin_id, admin_username)
                updated = container.repository.set_order_in_progress(order_id)
                container.repository.log_admin_action(order_id, admin_id, admin_username, "IN_PROGRESS")
                await callback.message.answer(f"IN_PROGRESS: {updated['order_id']}")

            elif action == "admin_done":
                if order.get("operator_id") and int(order["operator_id"]) != admin_id:
                    await callback.answer("Заказ занят другим оператором", show_alert=True)
                    return
                if order["status"] == OrderStatus.READY_FOR_OPERATOR.value:
                    if not order.get("operator_id"):
                        container.repository.claim_order(order_id, admin_id, admin_username)
                    container.repository.set_order_in_progress(order_id)
                updated = container.repository.mark_order_done(order_id)
                container.repository.log_admin_action(order_id, admin_id, admin_username, "DONE")
                await bot.send_message(
                    chat_id=int(updated["tg_id"]),
                    text=(
                        "Готово ✅ Проверьте, что подписка активна.\n"
                        "Нажмите одну кнопку ниже:"
                    ),
                    reply_markup=client_confirm_keyboard(updated["order_id"]),
                )
                await callback.message.answer(f"DONE: {updated['order_id']}")

            elif action == "admin_error":
                updated = container.repository.mark_order_error(
                    order_id=order_id,
                    error_code="OPERATOR_ERROR",
                    error_text="Оператор отметил ошибку выполнения",
                )
                container.repository.log_admin_action(order_id, admin_id, admin_username, "ERROR")
                await bot.send_message(
                    chat_id=int(updated["tg_id"]),
                    text=(
                        "Не получилось завершить заказ.\n"
                        "Оператор уже разбирается и свяжется с вами."
                    ),
                )
                await callback.message.answer(f"ERROR: {updated['order_id']}")

            elif action == "admin_template":
                product = container.products[order["product_code"]]
                await bot.send_message(
                    chat_id=int(order["tg_id"]),
                    text=product.instruction_template,
                )
                container.repository.log_admin_action(order_id, admin_id, admin_username, "SEND_TEMPLATE")
                await callback.message.answer(f"TEMPLATE SENT: {order['order_id']}")
            else:
                await callback.answer("Неизвестное действие", show_alert=True)
                return

        except Exception as exc:
            await callback.answer(f"Ошибка: {exc}", show_alert=True)
            return

        await callback.answer()

    return router


async def notify_payment_confirmed(container: AppContainer, bot: Bot, order: dict[str, Any]) -> None:
    product = container.products[order["product_code"]]
    guide_path = None
    if order["product_code"] not in {OPENROUTER_CODE, NANO_BANANA_CODE}:
        provider_guide = POST_PAYMENT_PROVIDER_GUIDE_BY_PROVIDER.get(product.provider)
        if provider_guide and provider_guide.exists():
            guide_path = provider_guide
        elif product.provider in {"gpt", "claude", "cursor", "copilot"} and DEFAULT_POST_PAYMENT_GUIDE_PATH.exists():
            guide_path = DEFAULT_POST_PAYMENT_GUIDE_PATH
    if guide_path is not None:
        await bot.send_photo(
            chat_id=int(order["tg_id"]),
            photo=FSInputFile(str(guide_path)),
        )
    await bot.send_message(
        chat_id=int(order["tg_id"]),
        text=ask_service_link_text(product),
    )
    await bot.send_message(
        chat_id=container.settings.admin_chat_id,
        text=admin_paid(order),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def send_renew_reminder(container: AppContainer, bot: Bot, tg_id: int, product_code: str, days_left: int) -> None:
    product = container.products.get(product_code)
    if product is None:
        return
    if days_left <= 0:
        text = (
            f"Подписка {product.name} истекает сегодня.\n"
            "Нажмите кнопку, чтобы продлить."
        )
    else:
        text = (
            f"До окончания подписки {product.name} осталось {days_left} дня.\n"
            "Нажмите кнопку, чтобы продлить."
        )
    await bot.send_message(
        chat_id=tg_id,
        text=text,
        reply_markup=renew_keyboard(product_code),
    )
