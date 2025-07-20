import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, executor
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

# ✅ Start background task
start_scheduler(bot)

# ✅ Fake Web Server for Render
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is running...")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# ✅ Start bot + web server together
if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    # Start the fake web server for Render
    loop.create_task(start_web_server())

    # Start the Telegram bot
    executor.start_polling(dp, skip_updates=True)
