from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.enums import OrderStatus
from app.state_machine import TransitionError, ensure_transition


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def iso_now() -> str:
    return utcnow().isoformat()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def _build_order_id() -> str:
    return f"RB-{utcnow():%Y%m%d%H%M%S}-{secrets.token_hex(2).upper()}"


@dataclass(slots=True)
class ActiveOrderExistsError(Exception):
    tg_id: int
    product_code: str
    existing_order_id: str | None = None

    def __str__(self) -> str:
        if self.existing_order_id:
            return (
                f"Active order exists for tg_id={self.tg_id} product={self.product_code}: "
                f"{self.existing_order_id}"
            )
        return f"Active order exists for tg_id={self.tg_id} product={self.product_code}"


class Repository:
    def __init__(self, database_path: str):
        self.database_path = database_path
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def upsert_user(self, tg_id: int, username: str | None, source_key: str | None) -> None:
        now = iso_now()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users (tg_id, username, first_seen_at, last_seen_at, source_key_last)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET
                  username=excluded.username,
                  last_seen_at=excluded.last_seen_at,
                  source_key_last=COALESCE(excluded.source_key_last, users.source_key_last)
                """,
                (tg_id, username, now, now, source_key),
            )
            conn.commit()

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? LIMIT 1",
                (order_id,),
            ).fetchone()
            return _row_to_dict(row)

    def get_order_by_payment_inv_id(self, inv_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE payment_inv_id = ? LIMIT 1",
                (inv_id,),
            ).fetchone()
            return _row_to_dict(row)

    def find_active_order(self, tg_id: int, product_code: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM orders
                WHERE tg_id = ? AND product_code = ?
                  AND status IN ('NEW','WAIT_PAY','PAID','WAIT_SERVICE_LINK','READY_FOR_OPERATOR','IN_PROGRESS','DONE','WAIT_CLIENT_CONFIRM')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (tg_id, product_code),
            ).fetchone()
            return _row_to_dict(row)

    def list_orders_by_user_and_statuses(self, tg_id: int, statuses: list[str]) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ",".join("?" for _ in statuses)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM orders
                WHERE tg_id = ? AND status IN ({placeholders})
                ORDER BY created_at DESC
                """,
                (tg_id, *statuses),
            ).fetchall()
            return [_row_to_dict(row) for row in rows if row is not None]

    def create_order(
        self,
        tg_id: int,
        username: str | None,
        source_key: str | None,
        product_code: str,
        product_name: str,
        price_rub: int,
        wait_pay_timeout_minutes: int,
    ) -> dict[str, Any]:
        order_id = _build_order_id()
        now = utcnow()
        expires_at = (now + timedelta(minutes=wait_pay_timeout_minutes)).isoformat()
        payload = (
            order_id,
            tg_id,
            username,
            source_key,
            product_code,
            product_name,
            price_rub,
            OrderStatus.NEW.value,
            now.isoformat(),
            now.isoformat(),
            expires_at,
            json.dumps({}),
        )

        with self._lock, self._connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO orders (
                      order_id, tg_id, username, source_key, product_code, product_name, price_rub, status,
                      created_at, updated_at, expires_at, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                order_db_id = cursor.lastrowid
                conn.execute(
                    "UPDATE orders SET payment_inv_id = ? WHERE id = ?",
                    (order_db_id, order_db_id),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                existing = self.find_active_order(tg_id=tg_id, product_code=product_code)
                raise ActiveOrderExistsError(
                    tg_id=tg_id,
                    product_code=product_code,
                    existing_order_id=existing["order_id"] if existing else None,
                )

        created = self.get_order(order_id)
        assert created is not None
        return created

    def update_payment_fields(
        self,
        order_id: str,
        out_sum: str | None,
        payment_status_text: str | None = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE orders
                SET payment_out_sum = COALESCE(?, payment_out_sum),
                    payment_status_text = COALESCE(?, payment_status_text),
                    updated_at = ?
                WHERE order_id = ?
                """,
                (out_sum, payment_status_text, iso_now(), order_id),
            )
            conn.commit()

    def transition_order(
        self,
        order_id: str,
        target_status: str,
        *,
        fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? LIMIT 1",
                (order_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Order not found: {order_id}")

            current_status = row["status"]
            try:
                ensure_transition(current=current_status, target=target_status)
            except TransitionError:
                if current_status == target_status:
                    result = _row_to_dict(row)
                    assert result is not None
                    return result
                raise

            updates: dict[str, Any] = fields.copy() if fields else {}
            updates["status"] = target_status
            updates["updated_at"] = iso_now()

            set_clause = ", ".join(f"{key} = ?" for key in updates.keys())
            values = list(updates.values()) + [order_id]
            conn.execute(
                f"UPDATE orders SET {set_clause} WHERE order_id = ?",
                values,
            )
            conn.commit()

            updated = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? LIMIT 1",
                (order_id,),
            ).fetchone()

        result = _row_to_dict(updated)
        assert result is not None
        return result

    def claim_order(self, order_id: str, operator_id: int, operator_username: str | None) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? LIMIT 1",
                (order_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Order not found: {order_id}")

            if row["status"] != OrderStatus.READY_FOR_OPERATOR.value:
                raise TransitionError(row["status"], OrderStatus.READY_FOR_OPERATOR.value)
            if row["operator_id"] and row["operator_id"] != operator_id:
                raise PermissionError("Order is already claimed by another operator.")

            fields: dict[str, Any] = {
                "operator_id": operator_id,
                "operator_username": operator_username,
            }
            if not row["claimed_at"]:
                fields["claimed_at"] = iso_now()

        return self.transition_order(
            order_id=order_id,
            target_status=OrderStatus.READY_FOR_OPERATOR.value,
            fields=fields,
        )

    def set_order_in_progress(self, order_id: str) -> dict[str, Any]:
        return self.transition_order(
            order_id=order_id,
            target_status=OrderStatus.IN_PROGRESS.value,
        )

    def set_service_link_ready(self, order_id: str, service_link: str) -> dict[str, Any]:
        return self.transition_order(
            order_id=order_id,
            target_status=OrderStatus.READY_FOR_OPERATOR.value,
            fields={
                "service_link": service_link,
                "service_link_received_at": iso_now(),
            },
        )

    def mark_order_done(self, order_id: str) -> dict[str, Any]:
        done = self.transition_order(
            order_id=order_id,
            target_status=OrderStatus.DONE.value,
            fields={"done_at": iso_now()},
        )
        return self.transition_order(
            order_id=order_id,
            target_status=OrderStatus.WAIT_CLIENT_CONFIRM.value,
        )

    def mark_order_error(self, order_id: str, error_code: str, error_text: str) -> dict[str, Any]:
        return self.transition_order(
            order_id=order_id,
            target_status=OrderStatus.ERROR.value,
            fields={"error_code": error_code, "error_text": error_text},
        )

    def mark_order_client_confirmed(self, order_id: str) -> dict[str, Any]:
        return self.transition_order(
            order_id=order_id,
            target_status=OrderStatus.CLIENT_CONFIRMED.value,
            fields={"client_confirmed_at": iso_now()},
        )

    def find_orders_for_wait_pay_timeout(self, now_dt: datetime, timeout_minutes: int) -> list[dict[str, Any]]:
        cutoff = (now_dt - timedelta(minutes=timeout_minutes)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM orders
                WHERE status = ? AND created_at <= ?
                """,
                (OrderStatus.WAIT_PAY.value, cutoff),
            ).fetchall()
            return [_row_to_dict(row) for row in rows if row is not None]

    def find_orders_for_wait_service_link_timeout(
        self,
        now_dt: datetime,
        timeout_hours: int,
    ) -> list[dict[str, Any]]:
        cutoff = (now_dt - timedelta(hours=timeout_hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM orders
                WHERE status = ? AND COALESCE(paid_at, updated_at) <= ?
                """,
                (OrderStatus.WAIT_SERVICE_LINK.value, cutoff),
            ).fetchall()
            return [_row_to_dict(row) for row in rows if row is not None]

    def upsert_subscription(
        self,
        tg_id: int,
        product_code: str,
        start_date_iso: str,
        end_date_iso: str,
        last_order_id: str,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO subscriptions (
                  tg_id, product_code, start_date, end_date, last_order_id, remind_3_sent, remind_0_sent
                ) VALUES (?, ?, ?, ?, ?, 0, 0)
                ON CONFLICT(tg_id, product_code) DO UPDATE SET
                  start_date=excluded.start_date,
                  end_date=excluded.end_date,
                  last_order_id=excluded.last_order_id,
                  remind_3_sent=0,
                  remind_0_sent=0
                """,
                (tg_id, product_code, start_date_iso, end_date_iso, last_order_id),
            )
            conn.commit()

    def list_subscriptions_due(self, today_utc: date) -> list[dict[str, Any]]:
        today_iso = today_utc.isoformat()
        plus_3 = (today_utc + timedelta(days=3)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM subscriptions
                WHERE end_date BETWEEN ? AND ?
                """,
                (today_iso, plus_3),
            ).fetchall()
            return [_row_to_dict(row) for row in rows if row is not None]

    def mark_subscription_reminder_sent(self, subscription_id: int, days_left: int) -> None:
        field = "remind_0_sent" if days_left <= 0 else "remind_3_sent"
        with self._lock, self._connect() as conn:
            conn.execute(
                f"UPDATE subscriptions SET {field} = 1 WHERE id = ?",
                (subscription_id,),
            )
            conn.commit()

    def log_admin_action(
        self,
        order_id: str,
        admin_id: int,
        admin_username: str | None,
        action: str,
        note: str | None = None,
    ) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_actions(order_id, admin_id, admin_username, action, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, admin_id, admin_username, action, note, iso_now()),
            )
            conn.commit()

    def log_event(self, event_type: str, payload: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events_log(event_type, payload_json, created_at)
                VALUES (?, ?, ?)
                """,
                (event_type, json.dumps(payload, ensure_ascii=False), iso_now()),
            )
            conn.commit()
