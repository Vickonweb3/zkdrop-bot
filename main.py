import logging
import os
import traceback  # 🔍 Imported to trace silent shutdowns

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config.settings import BOT_TOKEN
from handlers.start_handler import router as start_router
from handlers.airdrop_notify import router as airdrop_router
from handlers.admin_handler import router as admin_router
from handlers.menu_handler import router as menu_router
from utils.scheduler import start_scheduler

# ✅ Logging
logging.basicConfig(level=logging.INFO)

# ✅ Webhook settings
WEBHOOK_HOST = "https://zkdrop-bot.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# ✅ Health check routes
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is live...")

async def uptime_check(request):
    return web.Response(status=200, text="🟢 Uptime check OK")

# ✅ Main entry
def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # ✅ Register routers
    dp.include_router(start_router)
    dp.include_router(airdrop_router)
    dp.include_router(admin_router)
    dp.include_router(menu_router)

    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/uptime", uptime_check)

    # ✅ Webhook dispatcher
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    # ✅ Webhook & scheduler hooks
    async def on_startup(app):
        await bot.set_webhook(WEBHOOK_URL)
        logging.info("🚀 Webhook set successfully.")

        # ✅ Public Telegram menu (keep it clean — no admin-only commands)
        await bot.set_my_commands([
            BotCommand(command="start", description="Start or restart the bot"),
            BotCommand(command="menu", description="Open the main menu"),
        ])

        start_scheduler(bot)

    async def on_shutdown(app):
        # 🔍 Add stack trace to detect what's shutting down the app
        traceback.print_stack()
        await bot.delete_webhook()
        logging.warning("💤 Webhook shutdown initiated.")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()
