import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
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

# ✅ Bot & Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# ✅ Register routers (v3 style)
dp.include_router(start_router)
dp.include_router(airdrop_router)
dp.include_router(admin_router)
dp.include_router(menu_router)

# ✅ Webhook settings
WEBHOOK_HOST = "https://zkdrop-bot.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# ✅ Routes
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is live...")

async def uptime_check(request):
    return web.Response(status=200, text="🟢 Uptime check OK")

# ✅ Webhook + scheduler startup
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("🚀 Webhook set successfully.")
    start_scheduler(bot)

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("💤 Webhook shutdown initiated.")

def main():
    app = web.Application()

    # ✅ Add custom routes
    app.router.add_get("/", handle)
    app.router.add_get("/uptime", uptime_check)

    # ✅ Webhook dispatcher
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    # ✅ Setup startup & shutdown hooks
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # ✅ Launch app
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()
