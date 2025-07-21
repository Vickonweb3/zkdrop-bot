import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config.settings import BOT_TOKEN
from handlers import start_handler, airdrop_notify, admin_handler, menu_handler
from utils.scheduler import start_scheduler

# ✅ Logging
logging.basicConfig(level=logging.INFO)

# ✅ Bot & Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ✅ Register Handlers
start_handler.register_start(dp)
airdrop_notify.register_notify(dp)
admin_handler.register_admin(dp)
menu_handler.register_menu(dp)

# ✅ Start background scheduler
start_scheduler(bot)

# ✅ Webhook settings
WEBHOOK_HOST = "https://zkdrop-bot.onrender.com"  # Render link
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# ✅ AIOHTTP routes
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is live...")

async def uptime_check(request):
    return web.Response(status=200, text="🟢 Uptime check OK")

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("🚀 Webhook set successfully.")

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

    # ✅ Setup startup & shutdown
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    # ✅ Start app
    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()
