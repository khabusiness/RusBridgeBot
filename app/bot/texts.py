from __future__ import annotations

from app.products import Product

HELP_LINKS_BY_PROVIDER: dict[str, str] = {
    "claude": "https://rus-bridge.ru/help-claude.html",
    "cursor": "https://rus-bridge.ru/help-ide.html",
    "copilot": "https://rus-bridge.ru/help-ide.html",
    "openrouter": "https://rus-bridge.ru/help-openrouter.html",
}


def format_product_requirements(product: Product) -> str:
    if not product.requirements:
        return "Требования: уточним перед оплатой."
    req_lines = "\n".join(f"• {line}" for line in product.requirements)
    return f"Требования:\n{req_lines}"


def product_confirmation_text(product: Product) -> str:
    return (
        f"Вы хотите оформить: {product.name}\n"
        f"Цена: {product.price_label()}\n"
        f"Срок: {product.duration_days} дней\n\n"
        f"{format_product_requirements(product)}\n\n"
        "Если у вас нет VPN/аккаунта - оформление невозможно.\n"
        "Возврат возможен только до момента оплаты подписки.\n"
        "Услуга считается оказанной после выполнения согласованных действий.\n\n"
        "Действие: нажмите «Оформить»."
    )


def order_wait_pay_text(
    product: Product,
    order_id: str,
    payment_test_mode: bool,
    *,
    price_rub: int | None = None,
) -> str:
    amount_rub = price_rub if price_rub is not None else product.price_rub
    extra = ""
    if payment_test_mode:
        extra = (
            "\n\nРежим теста: используется заглушка оплаты."
            "\nПосле перехода по ссылке вернитесь в бот."
        )
    return (
        f"Заказ создан: {order_id}\n"
        f"Продукт: {product.name}\n"
        f"Сумма: {amount_rub} ₽\n\n"
        "Оплата подтверждается автоматически - скриншот не нужен.\n"
        "Действие: нажмите «Оплатить»."
        f"{extra}"
    )


def ask_service_link_text(product: Product) -> str:
    help_link = HELP_LINKS_BY_PROVIDER.get(product.provider)
    help_text = f"\nПомощь: {help_link}" if help_link else ""
    return (
        "Оплата подтверждена ✅\n\n"
        f"{product.service_link_prompt}\n"
        "Формат: одна ссылка в одном сообщении.\n"
        f"Действие: отправьте ссылку.{help_text}\n\n"
        "Если нужна помощь, напишите: МОД: ваш вопрос"
    )


def invalid_service_link_text(reason: str) -> str:
    return (
        "Ссылка выглядит неверно.\n"
        f"Причина: {reason}\n\n"
        "Действие: пришлите корректную ссылку."
    )


def admin_new_lead(order: dict, source_label: str) -> str:
    username = order.get("username")
    username_text = f"@{username}" if username else "без username"
    return (
        "NEW LEAD\n"
        f"Пользователь: {username_text} (id: {order['tg_id']})\n"
        f"Продукт: {order['product_name']}\n"
        f"Цена: {order['price_rub']} ₽\n"
        f"Источник: {source_label}\n"
        f"Order ID: {order['order_id']}\n"
        f"Статус: {order['status']}"
    )


def admin_paid(order: dict) -> str:
    return (
        "PAYMENT CONFIRMED\n"
        f"Order ID: {order['order_id']}\n"
        f"Продукт: {order['product_name']}\n"
        f"Сумма: {order.get('payment_out_sum') or order['price_rub']}\n"
        f"Статус: {order['status']}\n"
        "Теперь ждём ссылку сервиса."
    )


def admin_link_received(order: dict) -> str:
    return (
        "SERVICE LINK RECEIVED\n"
        f"Order ID: {order['order_id']}\n"
        f"Продукт: {order['product_name']}\n"
        f"Ссылка: {order['service_link']}\n"
        f"Статус: {order['status']}"
    )
