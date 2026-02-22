from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, RedirectResponse

from app.bot.handlers import notify_payment_confirmed
from app.runtime import AppContainer


def create_api(container: AppContainer, bot) -> FastAPI:
    app = FastAPI(title="RusBridgeBot API")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/payment/robokassa/result", response_class=PlainTextResponse)
    async def robokassa_result(request: Request) -> PlainTextResponse:
        form = await request.form()
        data = {str(key): str(value) for key, value in form.items()}
        if not container.payment_service.verify_result_signature(data):
            container.repository.log_event("robokassa_invalid_signature", data)
            raise HTTPException(status_code=400, detail="invalid signature")

        inv_id_raw = data.get("InvId", "")
        if not inv_id_raw.isdigit():
            raise HTTPException(status_code=400, detail="invalid inv_id")

        result = container.order_flow.handle_successful_payment_webhook(
            inv_id=int(inv_id_raw),
            out_sum=data.get("OutSum", ""),
            payment_status_text="webhook_paid",
        )
        container.repository.log_event(
            "robokassa_result_webhook",
            {
                "updated": result.updated,
                "reason": result.reason,
                "inv_id": inv_id_raw,
                "order_id": result.order["order_id"] if result.order else None,
            },
        )

        if result.updated and result.order is not None:
            await notify_payment_confirmed(container, bot, result.order)

        return PlainTextResponse(content=f"OK{inv_id_raw}")

    @app.get("/payment/robokassa/fail")
    async def robokassa_fail(request: Request) -> RedirectResponse:
        params = {str(key): str(value) for key, value in request.query_params.items()}
        inv_id_raw = params.get("InvId", "")
        redirect_to = f"https://t.me/{container.settings.bot_username}"
        order_id = None

        if inv_id_raw.isdigit():
            order = container.repository.get_order_by_payment_inv_id(int(inv_id_raw))
            if order is not None:
                order_id = order["order_id"]
                redirect_to = f"https://t.me/{container.settings.bot_username}?start=payfail_{order_id}"

        container.repository.log_event(
            "robokassa_fail_redirect",
            {
                "inv_id": inv_id_raw,
                "order_id": order_id,
                "params": params,
            },
        )
        return RedirectResponse(url=redirect_to, status_code=302)

    @app.get("/debug/storage")
    async def debug_storage() -> dict:
        import os

        storage_dir = "/data"
        if not os.path.isdir(storage_dir):
            return {"error": f"{storage_dir} is not mounted or does not exist", "files": []}

        files = []
        total_size = 0
        for file_name in sorted(os.listdir(storage_dir)):
            path = os.path.join(storage_dir, file_name)
            if not os.path.isfile(path):
                continue
            size = os.path.getsize(path)
            total_size += size
            files.append({"file": file_name, "size_bytes": size})

        return {"files": files, "total_size_bytes": total_size}

    return app
