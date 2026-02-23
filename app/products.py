from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROVIDER_ORDER = ("gpt", "openrouter", "nano", "claude", "cursor", "copilot", "other")
PROVIDER_TITLES: dict[str, str] = {
    "gpt": "GPT",
    "openrouter": "OpenRouter",
    "nano": "Nano Banana",
    "claude": "Claude",
    "cursor": "Cursor",
    "copilot": "Copilot",
    "other": "Other",
}


def infer_provider(product_code: str) -> str:
    if product_code == "openrouter":
        return "openrouter"
    for prefix, provider in (
        ("gpt_", "gpt"),
        ("nano_", "nano"),
        ("claude_", "claude"),
        ("cursor_", "cursor"),
        ("copilot_", "copilot"),
    ):
        if product_code.startswith(prefix):
            return provider
    return "other"


@dataclass(slots=True)
class Product:
    code: str
    name: str
    provider: str
    price_rub: int
    display_price: str | None
    duration_days: int
    requirements: list[str]
    service_link_prompt: str
    instruction_template: str
    allowed_domains: list[str]
    hidden: bool

    def price_label(self) -> str:
        if self.display_price:
            return self.display_price
        return f"{self.price_rub} ₽"


def load_products(path: str) -> dict[str, Product]:
    content = Path(path).read_text(encoding="utf-8")
    payload = json.loads(content)
    result: dict[str, Product] = {}
    for raw in payload:
        item = Product(
            code=raw["code"],
            name=raw["name"],
            provider=raw.get("provider", infer_provider(raw["code"])),
            price_rub=int(raw["price_rub"]),
            display_price=raw.get("display_price"),
            duration_days=int(raw["duration_days"]),
            requirements=list(raw.get("requirements", [])),
            service_link_prompt=raw.get("service_link_prompt", "Пришлите ссылку на оплату сервиса."),
            instruction_template=raw.get("instruction_template", "Инструкции отправит оператор."),
            allowed_domains=list(raw.get("allowed_domains", [])),
            hidden=bool(raw.get("hidden", False)),
        )
        result[item.code] = item
    return result
