from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  tg_id INTEGER PRIMARY KEY,
  username TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  source_key_last TEXT
);

CREATE TABLE IF NOT EXISTS blocked_users (
  tg_id INTEGER PRIMARY KEY,
  reason TEXT,
  blocked_by INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL UNIQUE,
  tg_id INTEGER NOT NULL,
  username TEXT,
  source_key TEXT,
  product_code TEXT NOT NULL,
  product_name TEXT NOT NULL,
  price_rub INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  expires_at TEXT,
  paid_at TEXT,
  service_link TEXT,
  service_link_received_at TEXT,
  operator_id INTEGER,
  operator_username TEXT,
  claimed_at TEXT,
  done_at TEXT,
  client_confirmed_at TEXT,
  payment_inv_id INTEGER UNIQUE,
  payment_out_sum TEXT,
  payment_status_text TEXT,
  error_code TEXT,
  error_text TEXT,
  metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_tg_id ON orders(tg_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_inv_id ON orders(payment_inv_id);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);

CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_one_active_per_service
ON orders(tg_id, product_code)
WHERE status IN ('NEW','WAIT_PAY','PAID','WAIT_SERVICE_LINK','READY_FOR_OPERATOR','IN_PROGRESS','DONE','WAIT_CLIENT_CONFIRM');

CREATE TABLE IF NOT EXISTS subscriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tg_id INTEGER NOT NULL,
  product_code TEXT NOT NULL,
  start_date TEXT NOT NULL,
  end_date TEXT NOT NULL,
  last_order_id TEXT NOT NULL,
  remind_3_sent INTEGER NOT NULL DEFAULT 0,
  remind_0_sent INTEGER NOT NULL DEFAULT 0,
  UNIQUE(tg_id, product_code)
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_end_date ON subscriptions(end_date);

CREATE TABLE IF NOT EXISTS admin_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL,
  admin_id INTEGER NOT NULL,
  admin_username TEXT,
  action TEXT NOT NULL,
  note TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  payload_json TEXT,
  created_at TEXT NOT NULL
);
"""


def init_db(database_path: str) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(database_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
