# Railway Deploy Checklist

## 1. Domain and SSL
1. Attach `api.rus-bridge.ru` to the Railway service.
2. Wait until SSL is issued.
3. Check `https://api.rus-bridge.ru/health` returns `{"status":"ok"}`.

## 2. Railway Variables
Set these variables in Railway:

1. `RUSBRIDGEBOT_TOKEN`
2. `RUSBRIDGEBOT_USERNAME=RusBridgeBot`
3. `RUSBRIDGECANNAL_CHAT_ID`
4. `USER_CHAT_ID`
5. `PAYMENT_MODE=manual`
6. `MANUAL_PAY_PHONE`
7. `MANUAL_PAY_BANKS`
8. `MANUAL_PAY_RECEIVER`
9. `MANUAL_PAY_CARD`
10. `PAYMENT_TEST_MODE=false`
11. `TEST_ID=false`
12. `DAILY_ORDER_LIMIT=5`
13. `OPERATOR_COOLDOWN_SECONDS=45`
14. `DEBUG_STORAGE_ENABLED=false`
15. `PRODUCTS_FILE=data/products.json`
16. `SQLITE_DB_PATH=/data/rusbridge.db`

If you switch to Robokassa later, also set:
- `ID_MAGAZIN_ROBOCASSA`
- `PASSWORD_1`
- `PASSWORD_2`
- `RESULT_URL=https://api.rus-bridge.ru/payment/robokassa/result`
- `SUCCESS_URL=https://rus-bridge.ru/success.html`
- `FAIL_URL=https://api.rus-bridge.ru/payment/robokassa/fail`
- `ROBOCASSA_HASH_ALGO=md5`
- `ROBOCASSA_IS_TEST=false`

## 3. SQLite volume
1. Add persistent volume.
2. Mount it to `/data`.
3. Keep `SQLITE_DB_PATH=/data/rusbridge.db`.

## 4. Manual payment checks
1. Ensure manual payment реквизиты are configured (`MANUAL_PAY_*`).
2. Create a test order and verify:
3. Button `Оплатить` opens payment details.
4. User can send screenshot.
5. Admin sees screenshot card with `PAYMENT DONE` / `REQUEST NEW SCREENSHOT`.
6. `PAYMENT DONE` moves order to `WAIT_SERVICE_LINK`.

## 5. Safe rollout
1. Deploy with `PAYMENT_MODE=manual`.
2. Test flow: create order -> open details -> send screenshot -> admin confirms -> send service link.
3. Test retry flow: admin requests new screenshot.

## 6. Go live
1. Keep `PAYMENT_MODE=manual`.
2. Keep `PAYMENT_TEST_MODE=false`.
3. Confirm operator playbook for payment screenshot verification.
