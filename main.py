import logging
import os
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
from handlers import support  # Added support handler
from utils.scheduler import start_scheduler
from pymongo import MongoClient

# ===== CRITICAL PLAYWRIGHT SETUP =====
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/tmp/ms-playwright'

os.makedirs('/tmp/ms-playwright/chromium-1105/chrome-linux', exist_ok=True, mode=0o777)

CHROME_PATH = '/tmp/ms-playwright/chromium-1105/chrome-linux/chrome'
if not os.path.exists(CHROME_PATH):
    os.system("wget -q https://playwright.azureedge.net/builds/chromium/1105/chromium-linux.zip -O /tmp/chromium.zip")
    os.system("unzip -q /tmp/chromium.zip -d /tmp/ms-playwright/chromium-1105")
    os.system("chmod +x /tmp/ms-playwright/chromium-1105/chrome-linux/chrome")

# =====================================

# ✅ Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://zkdrop-bot.onrender.com")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

last_webhook_hit = time.time()

# ===== MongoDB Setup =====
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["zkdrop_bot"]
tickets_collection = db["support_tickets"]
banned_collection = db["banned_users"]

# -----------------------------
# MongoDB helper functions
# -----------------------------
def get_next_ticket_number():
    last_ticket = tickets_collection.find_one(sort=[("ticket_number", -1)])
    return (last_ticket["ticket_number"] + 1) if last_ticket else 1

def log_support_ticket(ticket_id, user_id, username, category, message, status="Open"):
    ticket_number = int(ticket_id.split("-")[-1])
    tickets_collection.insert_one({
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "user_id": user_id,
        "username": username,
        "category": category,
        "message": message,
        "status": status,
        "timestamp": datetime.now()
    })

def get_ticket(ticket_id):
    return tickets_collection.find_one({"ticket_id": ticket_id})

def update_ticket_status(ticket_id, status):
    tickets_collection.update_one({"ticket_id": ticket_id}, {"$set": {"status": status}})

def log_banned_user(user_id):
    banned_collection.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

def remove_banned_user(user_id):
    banned_collection.delete_one({"user_id": user_id})

def get_banned_users():
    return [doc["user_id"] for doc in banned_collection.find()]

# -----------------------------
# Keep last_webhook_hit updated
# -----------------------------
async def keep_alive_telegram(bot: Bot):
    while True:
        try:
            me = await bot.get_me()
            logger.info(f"✅ Bot alive as @{me.username}")
        except Exception as e:
            logger.error(f"❌ Telegram ping failed: {e}")
            try:
                await bot.send_message(ADMIN_ID, f"🚨 *Telegram API down!*\n`{str(e)}`", parse_mode="Markdown")
            except Exception:
                logger.exception("Failed to notify admin")
        await asyncio.sleep(60)


async def periodic_webhook_reset(bot: Bot):
    while True:
        try:
            await bot.set_webhook(WEBHOOK_URL)
            logger.info("🔁 Webhook reset successful.")
        except Exception as e:
            logger.error(f"❌ Webhook reset failed: {e}")
            try:
                await bot.send_message(ADMIN_ID, f"🚨 *Webhook reset failed!*\n`{str(e)}`", parse_mode="Markdown")
            except Exception:
                logger.exception("Failed to notify admin")
        await asyncio.sleep(600)


async def monitor_webhook_inactivity(bot: Bot):
    global last_webhook_hit
    while True:
        now = time.time()
        if now - last_webhook_hit > 300:
            try:
                await bot.send_message(ADMIN_ID, "🚨 *No webhook updates in 5 minutes!*", parse_mode="Markdown")
                logger.warning("⚠️ Webhook inactive >5 mins.")
                last_webhook_hit = now
            except Exception:
                logger.exception("Failed to notify admin about inactivity")
        await asyncio.sleep(60)


# ✅ Web Handlers
async def handle(request):
    return web.Response(text="✅ ZK Drop Bot is live...")

async def uptime_check(request):
    return web.Response(status=200, text="🟢 Uptime check OK")

class CustomRequestHandler(SimpleRequestHandler):
    async def _handle(self, request: web.Request):
        global last_webhook_hit
        last_webhook_hit = time.time()
        return await super()._handle(request)


# =========================
# Main App Setup
# =========================
def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Include all routers
    dp.include_router(start_router)
    dp.include_router(airdrop_router)
    dp.include_router(admin_router)
    dp.include_router(menu_router)
    dp.include_router(support.router)  # <- support system

    app = web.Application()

    app.router.add_get("/", handle)
    app.router.add_get("/uptime", uptime_check)
    CustomRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    async def on_startup(app):
        await bot.set_webhook(WEBHOOK_URL)
        await bot.set_my_commands([
            BotCommand(command="start", description="Start or restart the bot"),
            BotCommand(command="menu", description="Open the main menu"),
        ])

        # Start background tasks
        app['telegram_heartbeat'] = asyncio.create_task(keep_alive_telegram(bot))
        app['webhook_monitor'] = asyncio.create_task(periodic_webhook_reset(bot))
        app['webhook_activity_checker'] = asyncio.create_task(monitor_webhook_inactivity(bot))

        # Start the scheduler for broadcasting/tasks
        start_scheduler(bot)
        logger.info("🚀 Bot fully initialized")

    async def on_shutdown(app):
        logger.warning("💤 Shutting down...")

        for task_name in ['telegram_heartbeat', 'webhook_monitor', 'webhook_activity_checker']:
            task = app.get(task_name)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        try:
            await bot.delete_webhook()
        except Exception:
            logger.exception("Failed to delete webhook during shutdown")

        logger.info("🛑 Bot shutdown complete")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))


if __name__ == "__main__":
    main()
