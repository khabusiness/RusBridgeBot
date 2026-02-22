from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings, load_settings
from app.db import init_db
from app.products import Product, load_products
from app.repository import Repository
from app.services.order_flow import OrderFlowService
from app.services.payment import RobokassaService


@dataclass(slots=True)
class AppContainer:
    settings: Settings
    products: dict[str, Product]
    repository: Repository
    payment_service: RobokassaService
    order_flow: OrderFlowService


def build_container() -> AppContainer:
    settings = load_settings()
    init_db(settings.database_path)
    products = load_products(settings.products_file)
    repository = Repository(settings.database_path)
    payment_service = RobokassaService(settings)
    flow = OrderFlowService(repository=repository, products=products, payment_service=payment_service, settings=settings)
    return AppContainer(
        settings=settings,
        products=products,
        repository=repository,
        payment_service=payment_service,
        order_flow=flow,
    )

