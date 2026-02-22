from __future__ import annotations

from dataclasses import dataclass

from app.enums import OrderStatus


@dataclass(slots=True)
class TransitionError(Exception):
    current: str
    target: str

    def __str__(self) -> str:
        return f"Invalid transition: {self.current} -> {self.target}"


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.NEW.value: {
        OrderStatus.WAIT_PAY.value,
        OrderStatus.CANCELLED.value,
        OrderStatus.EXPIRED.value,
    },
    OrderStatus.WAIT_PAY.value: {
        OrderStatus.PAID.value,
        OrderStatus.CANCELLED.value,
        OrderStatus.EXPIRED.value,
    },
    OrderStatus.PAID.value: {
        OrderStatus.WAIT_SERVICE_LINK.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.WAIT_SERVICE_LINK.value: {
        OrderStatus.READY_FOR_OPERATOR.value,
        OrderStatus.EXPIRED.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.READY_FOR_OPERATOR.value: {
        OrderStatus.IN_PROGRESS.value,
        OrderStatus.ERROR.value,
        OrderStatus.CANCELLED.value,
    },
    OrderStatus.IN_PROGRESS.value: {
        OrderStatus.DONE.value,
        OrderStatus.ERROR.value,
    },
    OrderStatus.DONE.value: {
        OrderStatus.WAIT_CLIENT_CONFIRM.value,
        OrderStatus.CLIENT_CONFIRMED.value,
    },
    OrderStatus.WAIT_CLIENT_CONFIRM.value: {
        OrderStatus.CLIENT_CONFIRMED.value,
        OrderStatus.ERROR.value,
    },
    OrderStatus.CLIENT_CONFIRMED.value: set(),
    OrderStatus.ERROR.value: set(),
    OrderStatus.EXPIRED.value: set(),
    OrderStatus.CANCELLED.value: set(),
}


def ensure_transition(current: str, target: str) -> None:
    if current == target:
        return
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise TransitionError(current=current, target=target)

