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
5. `ID_MAGAZIN_ROBOCASSA`
6. `PASSWORD_1`
7. `PASSWORD_2`
8. `RESULT_URL=https://api.rus-bridge.ru/payment/robokassa/result`
9. `SUCCESS_URL=https://rus-bridge.ru/success.html`
10. `FAIL_URL=https://api.rus-bridge.ru/payment/robokassa/fail`
11. `ROBOCASSA_HASH_ALGO=md5`
12. `ROBOCASSA_IS_TEST=false`
13. `PAYMENT_TEST_MODE=true` for first end-to-end check, then `false`
14. `PRODUCTS_FILE=data/products.json`
15. `SQLITE_DB_PATH=/data/rusbridge.db`

## 3. SQLite volume
1. Add persistent volume.
2. Mount it to `/data`.
3. Keep `SQLITE_DB_PATH=/data/rusbridge.db`.

## 4. Robokassa settings
1. Set `ResultURL` to `https://api.rus-bridge.ru/payment/robokassa/result`.
2. Set `SuccessURL` to `https://rus-bridge.ru/success.html`.
3. Set `FailURL` to `https://api.rus-bridge.ru/payment/robokassa/fail`.
4. Ensure password #1 and #2 match Railway variables.
5. Ensure hash algorithm matches `ROBOCASSA_HASH_ALGO`.

## 5. Safe rollout
1. Deploy with `PAYMENT_TEST_MODE=true`.
2. Test the flow in bot: create order -> test success -> send service link.
3. Test fail flow: open fail path and verify bot proposes retry/cancel.

## 6. Go live
1. Set `PAYMENT_TEST_MODE=false`.
2. Keep `ROBOCASSA_IS_TEST=false`.
3. Run one real payment.
4. Verify order transitions to `WAIT_SERVICE_LINK` via webhook.

