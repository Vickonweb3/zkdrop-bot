import logging
import os
import traceback
import asyncio
import time

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from config.settings import BOT_TOKEN, ADMIN_ID
from handlers.start_handler import router as start_router
from handlers.airdrop_notify import router as airdrop_router
from handlers.admin_handler import router as admin_router
from handlers.menu_handler import router as menu_router
from utils.scheduler import start_scheduler

# ✅ Logging
logging.basicConfig(level=logging.INFO)

WEBHOOK_HOST = "https://zkdrop-bot.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

last_webhook_hit = time.time()

# ✅ Health check
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is live...")

async def uptime_check(request):
    return web.Response(status=200, text="🟢 Uptime check OK")

# ✅ Ping Telegram every 1 min
async def keep_alive_telegram(bot: Bot):
    while True:
        try:
            me = await bot.get_me()
            logging.info(f"✅ Bot alive as @{me.username}")
        except Exception as e:
            logging.error(f"❌ Telegram ping failed: {e}")
            try:
                await bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *Telegram API down!*\n`{str(e)}`", parse_mode="Markdown")
            except: pass
        await asyncio.sleep(60)

# 🔁 Reset webhook every 10 min
async def periodic_webhook_reset(bot: Bot):
    while True:
        try:
            await bot.set_webhook(WEBHOOK_URL)
            logging.info("🔁 Webhook reset successful.")
        except Exception as e:
            logging.error(f"❌ Webhook reset failed: {e}")
            try:
                await bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *Webhook reset failed!*\n`{str(e)}`", parse_mode="Markdown")
            except: pass
        await asyncio.sleep(600)

# ⚠️ Alert if webhook silent for 5 min
async def monitor_webhook_inactivity(bot: Bot):
    global last_webhook_hit
    while True:
        now = time.time()
        if now - last_webhook_hit > 300:
            try:
                await bot.send_message(ADMIN_ID, "🚨 *No webhook updates in 5 minutes!*", parse_mode="Markdown")
                logging.warning("⚠️ Webhook inactive >5 mins.")
                last_webhook_hit = now
            except: pass
        await asyncio.sleep(60)

# ✅ Main
def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    dp.include_router(start_router)
    dp.include_router(airdrop_router)
    dp.include_router(admin_router)
    dp.include_router(menu_router)

    class CustomRequestHandler(SimpleRequestHandler):
        async def _handle(self, request: web.Request):
            global last_webhook_hit
            last_webhook_hit = time.time()
            return await super()._handle(request)

    app = web.Application()
    app.router.add_get("/", handle)
    app.router.add_get("/uptime", uptime_check)
    CustomRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    async def on_startup(app):
        await bot.set_webhook(WEBHOOK_URL)
        logging.info("🚀 Webhook set.")
        await bot.set_my_commands([
            BotCommand(command="start", description="Start or restart the bot"),
            BotCommand(command="menu", description="Open the main menu"),
        ])
        start_scheduler(bot)

        app['telegram_heartbeat'] = asyncio.create_task(keep_alive_telegram(bot))
        app['webhook_monitor'] = asyncio.create_task(periodic_webhook_reset(bot))
        app['webhook_activity_checker'] = asyncio.create_task(monitor_webhook_inactivity(bot))

    async def on_shutdown(app):
        traceback.print_stack()
        await bot.delete_webhook()
        logging.warning("💤 Webhook shutdown.")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()
