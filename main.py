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
from utils.scrapers.zealy import run_loop

# ===== CRITICAL PLAYWRIGHT SETUP =====
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = '/tmp/ms-playwright'

# Create directory structure with full permissions
os.makedirs('/tmp/ms-playwright/chromium-1105/chrome-linux', exist_ok=True, mode=0o777)

# Download and extract Chromium manually
CHROME_PATH = '/tmp/ms-playwright/chromium-1105/chrome-linux/chrome'
if not os.path.exists(CHROME_PATH):
    os.system("wget -q https://playwright.azureedge.net/builds/chromium/1105/chromium-linux.zip -O /tmp/chromium.zip")
    os.system("unzip -q /tmp/chromium.zip -d /tmp/ms-playwright/chromium-1105")
    os.system("chmod +x /tmp/ms-playwright/chromium-1105/chrome-linux/chrome")

# =====================================

# ✅ Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_HOST = "https://zkdrop-bot.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

last_webhook_hit = time.time()

# ✅ Background Tasks
async def zealy_scraper_task(bot: Bot):
    """Continuous Zealy scraping in background"""
    while True:
        try:
            logger.info("🔍 Running Zealy scraper...")
            await run_loop()  # Your existing scraper function
            await asyncio.sleep(60)  # Check every 60 seconds
        except Exception as e:
            logger.error(f"Scraper error: {e}")
            try:
                await bot.send_message(
                    ADMIN_ID,
                    f"🚨 Zealy Scraper Failed:\n<code>{str(e)[:200]}</code>",
                    parse_mode="HTML"
                )
            except:
                pass
            await asyncio.sleep(60)

async def keep_alive_telegram(bot: Bot):
    """Ping Telegram every 1 min"""
    while True:
        try:
            me = await bot.get_me()
            logger.info(f"✅ Bot alive as @{me.username}")
        except Exception as e:
            logger.error(f"❌ Telegram ping failed: {e}")
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🚨 *Telegram API down!*\n`{str(e)}`",
                    parse_mode="Markdown"
                )
            except:
                pass
        await asyncio.sleep(60)

async def periodic_webhook_reset(bot: Bot):
    """Reset webhook every 10 min"""
    while True:
        try:
            await bot.set_webhook(WEBHOOK_URL)
            logger.info("🔁 Webhook reset successful.")
        except Exception as e:
            logger.error(f"❌ Webhook reset failed: {e}")
            try:
                await bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🚨 *Webhook reset failed!*\n`{str(e)}`",
                    parse_mode="Markdown"
                )
            except:
                pass
        await asyncio.sleep(600)

async def monitor_webhook_inactivity(bot: Bot):
    """Alert if webhook silent for 5 min"""
    global last_webhook_hit
    while True:
        now = time.time()
        if now - last_webhook_hit > 300:
            try:
                await bot.send_message(
                    ADMIN_ID,
                    "🚨 *No webhook updates in 5 minutes!*",
                    parse_mode="Markdown"
                )
                logger.warning("⚠️ Webhook inactive >5 mins.")
                last_webhook_hit = now
            except:
                pass
        await asyncio.sleep(60)

# ✅ Web Handlers
async def handle(request):
    """Health check endpoint"""
    return web.Response(text="✅ ZK Drop Bot is live...")

async def uptime_check(request):
    """Uptime monitoring"""
    return web.Response(status=200, text="🟢 Uptime check OK")

class CustomRequestHandler(SimpleRequestHandler):
    """Track webhook activity"""
    async def _handle(self, request: web.Request):
        global last_webhook_hit
        last_webhook_hit = time.time()
        return await super()._handle(request)

# ✅ Main App Setup
def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()

    # Include all routers
    dp.include_router(start_router)
    dp.include_router(airdrop_router)
    dp.include_router(admin_router)
    dp.include_router(menu_router)

    app = web.Application()
    
    # Register routes
    app.router.add_get("/", handle)
    app.router.add_get("/uptime", uptime_check)
    CustomRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

    # Startup/Shutdown handlers
    async def on_startup(app):
        """Initialize everything when starting"""
        await bot.set_webhook(WEBHOOK_URL)
        await bot.set_my_commands([
            BotCommand(command="start", description="Start or restart the bot"),
            BotCommand(command="menu", description="Open the main menu"),
        ])
        
        # Start all background tasks
        app['zealy_scraper'] = asyncio.create_task(zealy_scraper_task(bot))
        app['telegram_heartbeat'] = asyncio.create_task(keep_alive_telegram(bot))
        app['webhook_monitor'] = asyncio.create_task(periodic_webhook_reset(bot))
        app['webhook_activity_checker'] = asyncio.create_task(monitor_webhook_inactivity(bot))
        
        start_scheduler(bot)
        logger.info("🚀 Bot fully initialized")

    async def on_shutdown(app):
        """Cleanup before shutdown"""
        logger.warning("💤 Shutting down...")
        
        # Cancel all background tasks
        for task in [
            'zealy_scraper',
            'telegram_heartbeat',
            'webhook_monitor',
            'webhook_activity_checker'
        ]:
            if task in app:
                app[task].cancel()
                try:
                    await app[task]
                except asyncio.CancelledError:
                    pass
                    
        await bot.delete_webhook()
        logger.info("🛑 Bot shutdown complete")

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    setup_application(app, dp, bot=bot)

    web.run_app(app, host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    main()
