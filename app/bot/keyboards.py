from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.products import PROVIDER_ORDER, PROVIDER_TITLES, Product


def provider_picker_keyboard(products: dict[str, Product]) -> InlineKeyboardMarkup:
    available = {product.provider for product in products.values() if not product.hidden}
    rows: list[list[InlineKeyboardButton]] = []
    for provider in PROVIDER_ORDER:
        if provider not in available:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=PROVIDER_TITLES.get(provider, provider.title()),
                    callback_data=f"provider:{provider}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def product_picker_keyboard(
    products: dict[str, Product],
    *,
    provider: str | None = None,
    include_back: bool = False,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for code, product in products.items():
        if product.hidden:
            continue
        if provider and product.provider != provider:
            continue
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{product.name} - {product.price_label()}",
                    callback_data=f"product:{code}",
                )
            ]
        )
    if include_back:
        rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="providers")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_product_keyboard(product_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Оформить", callback_data=f"confirm:{product_code}")],
        ]
    )


def payment_keyboard(
    payment_url: str,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="💳 Оплатить", url=payment_url)]]
    )


def payment_test_confirm_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Симулировать оплату", callback_data=f"test_paid:{order_id}")]
        ]
    )


def payment_test_fail_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Тест отказа оплаты", callback_data=f"test_fail:{order_id}")],
        ]
    )


def payment_retry_keyboard(payment_url: str, order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить снова", url=payment_url)],
            [InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel:{order_id}")],
        ]
    )


def client_confirm_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Активно", callback_data=f"client_ok:{order_id}")],
            [InlineKeyboardButton(text="❓ Вопрос оператору", callback_data=f"client_fail:{order_id}")],
        ]
    )


def admin_order_keyboard(order_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ CLAIM", callback_data=f"admin_claim:{order_id}")],
            [InlineKeyboardButton(text="🟡 IN_PROGRESS", callback_data=f"admin_progress:{order_id}")],
            [InlineKeyboardButton(text="✅ DONE", callback_data=f"admin_done:{order_id}")],
            [InlineKeyboardButton(text="🔴 ERROR", callback_data=f"admin_error:{order_id}")],
            [InlineKeyboardButton(text="🧾 SEND TEMPLATE", callback_data=f"admin_template:{order_id}")],
        ]
    )


def renew_keyboard(product_code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔃 Продлить", callback_data=f"renew:{product_code}")],
        ]
    )
