from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse

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

    return app

