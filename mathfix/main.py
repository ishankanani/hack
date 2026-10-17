"""Entry point: `python -m mathfix.main`.

MODE=polling  -> local development (no domain needed)
MODE=webhook  -> server: aiohttp app with /tg/webhook and /health (behind Cloudflare Tunnel)
"""
from __future__ import annotations

import asyncio
import os
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from .ai.router import Router as AIRouter
from .bot import admin, handlers
from .config import Settings, load_settings
from .core.limits import Limits
from .core.pipeline import Pipeline
from .core.tutor import Tutor
from .db import Repo
from .mathcheck.sandbox import Sandbox

log = logging.getLogger("mathfix")
WEBHOOK_PATH = "/tg/webhook"


async def monitor(bot: Bot, settings: Settings, ai: AIRouter, limits: Limits, repo: Repo) -> None:
    """Every minute: quota alerts (70 % / 90 %) and guard-mode changes to the admin chat; daily pruning."""
    sent: set[tuple] = set()
    last_mode = "normal"
    last_prune = ""
    while True:
        try:
            day = ai.budget.day
            if settings.admin_chat_id:
                for spec in ai.specs.values():
                    if not spec.enabled:
                        continue
                    used = ai.budget.fraction_used(spec)
                    for level in (0.7, 0.9):
                        if used >= level and (day, spec.name, level) not in sent:
                            sent.add((day, spec.name, level))
                            await bot.send_message(settings.admin_chat_id,
                                                   f"📈 {spec.name} at {used:.0%} of today's free quota",
                                                   parse_mode=None)
                mode = await limits.guard_mode()
                if mode != last_mode:
                    await bot.send_message(settings.admin_chat_id, f"🛡 Capacity guard: {last_mode} → {mode}",
                                           parse_mode=None)
                    last_mode = mode
            if last_prune != day:
                await repo.prune()
                last_prune = day
        except Exception:  # noqa: BLE001 - monitoring must never crash the bot
            log.exception("monitor tick failed")
        await asyncio.sleep(60)


async def build() -> tuple[Settings, Bot, Dispatcher, dict]:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not settings.bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set (copy .env.example to .env)")
    repo = Repo(settings.database_path)
    await repo.init()
    sandbox = Sandbox(workers=int(os.environ.get("SANDBOX_WORKERS", "2")))
    await sandbox.start()
    ai = AIRouter(settings.models, repo)
    await ai.start()
    limits = Limits(settings, repo, ai)
    deps = dict(settings=settings, repo=repo, sandbox=sandbox, ai=ai, limits=limits,
                pipeline=Pipeline(ai, repo, sandbox), tutor=Tutor(ai, repo))
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(**deps)
    dp.include_router(admin.setup(settings.admin_user_ids))
    dp.include_router(handlers.router)
    return settings, bot, dp, deps


async def shutdown(deps: dict) -> None:
    await deps["ai"].close()
    await deps["sandbox"].close()
    await deps["repo"].close()


async def run_polling() -> None:
    settings, bot, dp, deps = await build()
    task = asyncio.create_task(monitor(bot, settings, deps["ai"], deps["limits"], deps["repo"]))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        log.info("MathFix running in polling mode")
        await dp.start_polling(bot)
    finally:
        task.cancel()
        await shutdown(deps)


def run_webhook() -> None:
    async def make_app() -> web.Application:
        settings, bot, dp, deps = await build()
        app = web.Application(client_max_size=12 * 1024 * 1024)

        async def health(_request):
            ok = await deps["repo"].ping()
            return web.json_response({"ok": ok}, status=200 if ok else 503)

        async def on_startup(_app):
            await bot.set_webhook(f"{settings.webhook_base_url}{WEBHOOK_PATH}", secret_token=settings.webhook_secret,
                                  allowed_updates=["message", "callback_query"], max_connections=40)
            app["monitor"] = asyncio.create_task(monitor(bot, settings, deps["ai"], deps["limits"], deps["repo"]))

        async def on_cleanup(_app):
            app["monitor"].cancel()
            await shutdown(deps)

        app.router.add_get("/health", health)
        SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=settings.webhook_secret).register(app, WEBHOOK_PATH)
        setup_application(app, dp, bot=bot)
        app.on_startup.append(on_startup)
        app.on_cleanup.append(on_cleanup)
        app["port"] = settings.port
        return app

    settings = load_settings()
    if not settings.webhook_base_url or not settings.webhook_secret:
        raise SystemExit("MODE=webhook needs WEBHOOK_BASE_URL and TELEGRAM_WEBHOOK_SECRET")
    web.run_app(make_app(), host="127.0.0.1", port=settings.port)


def main() -> None:
    settings = load_settings()
    if settings.mode == "webhook":
        run_webhook()
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
