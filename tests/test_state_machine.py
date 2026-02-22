from __future__ import annotations

import pytest

from app.state_machine import TransitionError, ensure_transition


def test_valid_transition_chain() -> None:
    ensure_transition("NEW", "WAIT_PAY")
    ensure_transition("WAIT_PAY", "PAID")
    ensure_transition("PAID", "WAIT_SERVICE_LINK")
    ensure_transition("WAIT_SERVICE_LINK", "READY_FOR_OPERATOR")
    ensure_transition("READY_FOR_OPERATOR", "IN_PROGRESS")
    ensure_transition("IN_PROGRESS", "DONE")
    ensure_transition("DONE", "WAIT_CLIENT_CONFIRM")
    ensure_transition("WAIT_CLIENT_CONFIRM", "CLIENT_CONFIRMED")


def test_invalid_transition_raises() -> None:
    with pytest.raises(TransitionError):
        ensure_transition("WAIT_PAY", "READY_FOR_OPERATOR")

