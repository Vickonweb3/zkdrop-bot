import logging
import os
import traceback
import asyncio  # 🧠 Needed for keep-alive and scheduler

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

# ✅ Webhook settings
WEBHOOK_HOST = "https://zkdrop-bot.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# ✅ Health check routes
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is live...")

async def uptime_check(request):
    return web.Response(status=200, text="🟢 Uptime check OK")

# ✅ Keep Telegram alive every 1 minute — with admin alert
async def keep_alive_telegram(bot: Bot):
    while True:
        try:
            me = await bot.get_me()
            logging.info(f"✅ Telegram bot alive as @{me.username}")
        except Exception as e:
            logging.error(f"❌ Telegram API ping failed: {e}")
            try:
                await bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *Bot failed to ping Telegram API!*\n\n`{str(e)}`", parse_mode="Markdown")
            except Exception as err:
                logging.error(f"❌ Failed to send Telegram alert: {err}")
        await asyncio.sleep(60)

# 🔁 Reset webhook every 10 minutes — with admin alert
async def periodic_webhook_reset(bot: Bot):
    while True:
        try:
            await bot.set_webhook(WEBHOOK_URL)
            logging.info("🔁 Webhook reset successful.")
        except Exception as e:
            logging.error(f"❌ Failed to reset webhook: {e}")
            try:
                await bot.send_message(chat_id=ADMIN_ID, text=f"🚨 *Webhook reset failed!*\n\n`{str(e)}`", parse_mode="Markdown")
            except Exception as err:
                logging.error(f"❌ Failed to send webhook alert: {err}")
        await asyncio.sleep(600)

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

        await bot.set_my_commands([
            BotCommand(command="start", description="Start or restart the bot"),
            BotCommand(command="menu", description="Open the main menu"),
        ])

        start_scheduler(bot)

        # ✅ Start keep-alive tasks
        app['telegram_heartbeat'] = asyncio.create_task(keep_alive_telegram(bot))
        app['webhook_monitor'] = asyncio.create_task(periodic_webhook_reset(bot))

    async def on_shutdown(app):
        traceback.print_stack()
        await bot.delete_webhook()
        logging.warning("💤 Webhook shutdown initiated.")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    setup_application(app, dp, bot=bot)
    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()
