# RusBridgeBot (Python)

Telegram bot for selling subscription setup services with:
- Robokassa payment links and webhook confirmation
- operator workflow in a Telegram admin chat
- SQLite persistence
- FastAPI web endpoints for payment callbacks

UI messages are currently in Russian; this README is in English for maintenance.

## What Is Implemented

1. Strict order state machine with explicit statuses.
2. One active (non-terminal) order per user at a time.
3. Two-step catalog UX: provider -> product.
4. Fixed-price and variable-price products.
5. Service payment-link validation by URL format and per-product domain allowlist.
6. Operator actions from admin chat via inline buttons.
7. Customer-to-operator escalation from any step via `/operator` or `MOD: ...` (including Russian keyboard variant).
8. Admin proactive messaging to users via `/msg <tg_id|order_id> <text>`.
9. Optional guide images before/after payment for selected providers.
10. Renewal reminders based on `subscriptions` data.
11. Anti-abuse controls: per-user open-order lock, daily order limit, operator request cooldown.
12. Admin moderation controls: `/block`, `/unblock`, `/close`.

## Order Statuses

- `NEW`
- `WAIT_PAY`
- `PAID`
- `WAIT_SERVICE_LINK`
- `READY_FOR_OPERATOR`
- `IN_PROGRESS`
- `DONE`
- `WAIT_CLIENT_CONFIRM`
- `CLIENT_CONFIRMED`
- `ERROR`
- `EXPIRED`
- `CANCELLED`

`WAIT_CLIENT_CONFIRM` separates "operator marked done" from "customer confirmed activation".

## Customer Flow

1. User starts with `/start` (or deep link like `/start gpt_plus_1m`).
2. User picks provider and product (or enters custom USD amount for variable-price products).
3. Bot creates/resumes order and sends payment link.
4. Payment is confirmed by webhook (`/payment/robokassa/result`) or by test action when test mode is enabled.
5. Bot asks for the service payment link.
6. Link is validated and sent to admin workflow.
7. Operator processes order (`CLAIM -> IN_PROGRESS -> DONE`).
8. User confirms activation (`CLIENT_CONFIRMED`) or reports issue.

## Customer Commands

- `/start` - open product flow.
- `/help` - short flow and command guide.
- `/status [order_id]` - show status for one order or current active order.
- `/cancel <order_id>` - cancel when transition is allowed.
- `/operator` - request operator assistance.
- `MOD: your question` - send a direct question to operator from any stage.

## Admin Workflow

Admin chat receives cards/events:
- `NEW LEAD`
- `PAYMENT CONFIRMED`
- `SERVICE LINK RECEIVED`
- issue/timeout/cancellation events

Admin inline actions:
- `CLAIM`
- `IN_PROGRESS`
- `DONE`
- `ERROR`
- `SEND TEMPLATE`

Admin text command:
- `/msg <tg_id|order_id> <text>` - send a message to a specific user by Telegram ID or `RB-...` order ID.
- `/block <tg_id|order_id> [reason]` - block user from bot actions.
- `/unblock <tg_id|order_id>` - remove block.
- `/close <order_id> <cancel|error> [reason]` - manually close an order.

## Abuse and Security Protection

- Open-order lock:
  - a user cannot create a new order while any existing order is still in a non-terminal status
  - this prevents creating many parallel unpaid/in-progress orders
- Daily order limit:
  - max N new orders per user per UTC day (`DAILY_ORDER_LIMIT`, default `5`)
  - bypass switch for internal testing: `TEST_ID=true`
- Operator request cooldown:
  - `/operator`, `MOD: ...`, and operator-callback requests are rate-limited per user
  - configured by `OPERATOR_COOLDOWN_SECONDS` (default `45`)
- User blocking:
  - blocked users are denied all bot actions in private flow and callbacks
  - controlled by admin commands `/block` and `/unblock`
- Manual admin closure:
  - `/close <order_id> <cancel|error> [reason]` can force close stuck/problem orders
  - closure is logged to `admin_actions`
- Webhook hardening:
  - Robokassa `SignatureValue` check
  - strict `Shp_order_id` match with expected `order_id`
  - strict `OutSum` match with expected order amount
- Debug endpoint safety:
  - `/debug/storage` is disabled by default
  - enable explicitly with `DEBUG_STORAGE_ENABLED=true`

## Product Model and Catalog

Products are configured in `data/products.json`.

Some fixed Nano plans exist but are hidden (`hidden: true`) because Nano is currently sold as custom amount input.

### Variable-Price Products

For `openrouter` and `nano_banana`, user enters an integer USD amount.
Bot calculates order amount in RUB using:

`price_rub = int(usd_amount * 1.3 * 80)`

## Guide Images

Optional local image files used by bot:

- `data/Nano.jpg`:
  - shown for Nano flow before asking user to enter USD amount
- `data/GPT.jpg`:
  - shown after payment confirmation for GPT
  - fallback image for Claude/Cursor/Copilot if provider-specific image is missing
- provider-specific post-payment images (when present):
  - `data/Cloude.jpg`
  - `data/Cursore.jpg`
  - `data/Copilot.jpg`

No post-payment guide image is sent for `openrouter` and `nano_banana`.

## Robokassa Integration

Implemented:
- payment link generation
- signature generation (`ROBOCASSA_HASH_ALGO`, default `md5`)
- webhook signature verification using `PASSWORD_2`
- idempotent handling of repeated paid webhooks

Notes:
- only `ResultURL` webhook confirms payment in the order model
- webhook request must pass `SignatureValue`, `Shp_order_id`, and `OutSum` checks
- fail/expired browser redirects are not treated as paid events
- expiration handled by internal timeout jobs (`WAIT_PAY_TIMEOUT_MINUTES`, `WAIT_SERVICE_LINK_TIMEOUT_HOURS`)

## HTTP Endpoints

- `GET /health`
- `POST /payment/robokassa/result`
- `GET /payment/robokassa/fail`
- `GET /debug/storage` (ops/debug helper, only when `DEBUG_STORAGE_ENABLED=true`)

## SQLite Tables

- `users`
- `blocked_users`
- `orders`
- `subscriptions`
- `admin_actions`
- `events_log`

## Environment Variables

See `.env.example` for full list.

Core variables:
- `RUSBRIDGEBOT_TOKEN`
- `RUSBRIDGEBOT_USERNAME`
- `RUSBRIDGECANNAL_CHAT_ID`
- `USER_CHAT_ID`
- `ID_MAGAZIN_ROBOCASSA`
- `PASSWORD_1`
- `PASSWORD_2`
- `ROBOCASSA_HASH_ALGO`
- `ROBOCASSA_IS_TEST`
- `RESULT_URL`
- `SUCCESS_URL`
- `FAIL_URL`
- `PAYMENT_TEST_MODE`
- `TEST_ID`
- `DAILY_ORDER_LIMIT`
- `SQLITE_DB_PATH`
- `PRODUCTS_FILE`
- `OPERATOR_COOLDOWN_SECONDS`
- `DEBUG_STORAGE_ENABLED`

Go-live settings for real production payments:
- `PAYMENT_TEST_MODE=false`
- `ROBOCASSA_IS_TEST=false`

## Local Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

The app runs both:
- Telegram polling worker
- FastAPI server (Uvicorn) in the same process

## Tests

```bash
python -m pytest -q
```

Unit tests cover:
- state-machine transitions
- service-link validation
- Robokassa signatures
- one-active-order invariant
- paid-webhook idempotency

## Deployment

- `Procfile` and `railway.json` are included.
- Railway checklist: `DEPLOY_RAILWAY.md`.
