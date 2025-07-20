import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
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
WEBHOOK_HOST = "https://zkdrop-bot.onrender.com"  # your Render link
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# ✅ Webhook startup
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info("🚀 Webhook set successfully.")

# ✅ Webhook shutdown
async def on_shutdown(dp):
    logging.info("💤 Webhook shutdown initiated.")
    await bot.delete_webhook()

# ✅ AIOHTTP route for webhook (Render requires this to keep container awake)
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is live...")

# ✅ fake route for uptime bot they wont know what hit them 
async def uptime_check(request):
    return web.Response(status=200, text="🟢 Uptime check OK")

# ✅ AIOHTTP app
def get_app():
    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/uptime", uptime_check)
    return app

# ✅ Start bot using webhook
if __name__ == "__main__":
    # Bind your Dispatcher to webhook handler
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 10000)),
        web_app=get_app(),  # Attach fake web server
)
