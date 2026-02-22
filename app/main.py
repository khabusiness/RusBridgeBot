from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot, Dispatcher

from app.api import create_api
from app.bot.handlers import build_router
from app.jobs import build_scheduler
from app.runtime import build_container


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    container = build_container()
    bot = Bot(token=container.settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(container=container, bot=bot))

    scheduler = build_scheduler(container, bot)
    scheduler.start()

    api = create_api(container=container, bot=bot)
    config = uvicorn.Config(
        app=api,
        host=container.settings.web_host,
        port=container.settings.web_port,
        log_level="info",
    )
    server = uvicorn.Server(config=config)

    polling_task = asyncio.create_task(
        dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    )
    api_task = asyncio.create_task(server.serve())

    done, pending = await asyncio.wait(
        {polling_task, api_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()

    scheduler.shutdown(wait=False)
    await bot.session.close()

    for task in done:
        if task.cancelled():
            continue
        exc = task.exception()
        if exc:
            raise exc


if __name__ == "__main__":
    asyncio.run(run())
