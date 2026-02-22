# Railway Deploy Checklist

## 1. Подготовка доменов

1. Привяжите `api.rus-bridge.ru` к Railway сервису.
2. Убедитесь, что SSL сертификат выдан и активен.
3. Проверьте `GET https://api.rus-bridge.ru/health` -> `{"status":"ok"}`.

## 2. Переменные Railway

Установите в Railway Variables:

1. `RUSBRIDGEBOT_TOKEN`
2. `RUSBRIDGECANNAL_CHAT_ID`
3. `USER_CHAT_ID`
4. `ID_MAGAZIN_ROBOCASSA`
5. `PASSWORD_1`
6. `PASSWORD_2`
7. `RESULT_URL=https://api.rus-bridge.ru/payment/robokassa/result`
8. `SUCCESS_URL=https://rus-bridge.ru/success.html`
9. `FAIL_URL=https://rus-bridge.ru/fail.html`
10. `ROBOCASSA_HASH_ALGO=md5`
11. `ROBOCASSA_IS_TEST=false` (для боевого режима)
12. `PAYMENT_TEST_MODE=true` (первый прогон), затем `false`
13. `PRODUCTS_FILE=data/products.json`
14. `SQLITE_DB_PATH=/data/rusbridge.db`

## 3. Хранилище SQLite

1. Добавьте persistent volume в Railway.
2. Смонтируйте volume в `/data`.
3. Проверьте, что `SQLITE_DB_PATH=/data/rusbridge.db`.

## 4. Настройка Robokassa

1. В кабинете укажите `ResultURL`: `https://api.rus-bridge.ru/payment/robokassa/result`.
2. Убедитесь, что пароль #1/#2 совпадает с Railway Variables.
3. Убедитесь, что алгоритм подписи в кабинете совпадает с `ROBOCASSA_HASH_ALGO`.
4. Проверьте `SuccessURL` и `FailURL` в кабинете.

## 5. Первичный запуск (safe)

1. Разверните с `PAYMENT_TEST_MODE=true`.
2. Пройдите полный сценарий в боте через кнопку `🧪 Симулировать оплату`.
3. Проверьте карточки в админ-группе: `NEW LEAD`, `SERVICE LINK RECEIVED`, `DONE`.

## 6. Переключение в боевой режим

1. Установите `PAYMENT_TEST_MODE=false`.
2. Оставьте `ROBOCASSA_IS_TEST=false` для боевого магазина.
3. Пройдите реальный платёж на малую сумму.
4. Убедитесь, что webhook дал `OK<InvId>` и заказ перешёл в `WAIT_SERVICE_LINK`.

## 7. Финальная проверка

1. Проверить `/status <order_id>` в клиентском чате.
2. Проверить `CLAIM -> IN_PROGRESS -> DONE` в админ-группе.
3. Проверить создание записи в `subscriptions` после `✅ Активно`.
4. Проверить напоминания о продлении (можно тестово поставить близкий `end_date`).

