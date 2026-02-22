from __future__ import annotations

from enum import StrEnum


class OrderStatus(StrEnum):
    NEW = "NEW"
    WAIT_PAY = "WAIT_PAY"
    PAID = "PAID"
    WAIT_SERVICE_LINK = "WAIT_SERVICE_LINK"
    READY_FOR_OPERATOR = "READY_FOR_OPERATOR"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    WAIT_CLIENT_CONFIRM = "WAIT_CLIENT_CONFIRM"
    CLIENT_CONFIRMED = "CLIENT_CONFIRMED"
    ERROR = "ERROR"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


ACTIVE_ORDER_STATUSES = {
    OrderStatus.NEW.value,
    OrderStatus.WAIT_PAY.value,
    OrderStatus.PAID.value,
    OrderStatus.WAIT_SERVICE_LINK.value,
    OrderStatus.READY_FOR_OPERATOR.value,
    OrderStatus.IN_PROGRESS.value,
    OrderStatus.DONE.value,
    OrderStatus.WAIT_CLIENT_CONFIRM.value,
}


TERMINAL_ORDER_STATUSES = {
    OrderStatus.CLIENT_CONFIRMED.value,
    OrderStatus.ERROR.value,
    OrderStatus.EXPIRED.value,
    OrderStatus.CANCELLED.value,
}

