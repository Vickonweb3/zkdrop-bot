# utils/scheduler.py
import os
import asyncio
import logging
from datetime import datetime
from typing import Any, List

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import utc

from config.settings import TASK_INTERVAL_MINUTES, DAILY_HOUR_UTC
from database.db import get_unposted_airdrop, mark_airdrop_posted
from utils.task.send_airdrop import send_airdrop_to_all
from utils.scam_analyzer import analyze_airdrop
from utils.twitter_rating import rate_twitter_buzz

try:
    from utils.scrapers import zealy as zealy_scraper
except Exception:
    zealy_scraper = None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------- Format Messages ----------
def format_user_message(airdrop: dict) -> str:
    title = airdrop.get("title", "Unknown")
    xp = airdrop.get("xp", "N/A")
    description = airdrop.get("description", "No description")
    link = airdrop.get("link", "#")
    if len(description) > 120:
        description = description[:120] + "..."
    return (
        f"🚀 *New Airdrop Alert!*\n\n"
        f"🔹 *{title}*\n"
        f"💎 XP: {xp}\n\n"
        f"📖 {description}\n\n"
        f"👉 [Join Airdrop]({link})"
    )

def format_admin_message(airdrop: dict, scam_summary=None, twitter_buzz=None) -> str:
    title = airdrop.get("title", "Unknown")
    xp = airdrop.get("xp", "N/A")
    description = airdrop.get("description", "No description")
    link = airdrop.get("link", "#")
    scam_text = "Not checked"
    if scam_summary:
        scam_text = f"Score: {scam_summary.get('score')}, Verdict: {scam_summary.get('verdict')}"
    buzz_text = f"Twitter Buzz: {twitter_buzz}" if twitter_buzz else "Twitter: N/A"
    return (
        f"📢 *New Airdrop Detected*\n\n"
        f"🔹 *Title:* {title}\n"
        f"💎 *XP:* {xp}\n"
        f"📖 *Description:* {description}\n"
        f"🔗 *Link:* {link}\n"
        f"🕒 *Detected:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"⚠️ *Scam Check:* {scam_text}\n"
        f"🔥 *{buzz_text}*"
    )

# ---------- Scraper ----------
# utils/scheduler.py
# ... (keep the rest of the file as-is, only replace the function below)

async def run_scraper_once(limit=25) -> List[dict]:
    """
    Tries to call the available scraper function on the imported zealy_scraper module.
    The scraper module historically exposed different names in different versions:
      - run_scrape_once(limit=...)
      - run_once(limit=...)
      - scrape_once(limit=...)
      - run_loop(poll_interval=..., daily_hour=...)  <-- we won't call run_loop for a single run unless needed

    This function tries to find the appropriate callable, runs it (awaiting if coroutine),
    and returns its result (list of dicts). If no function is found, it returns [].
    """
    if not zealy_scraper:
        logger.warning("No Zealy scraper found.")
        return []

    # Prefer the explicit per-run function name used in this repository
    fn = (
        getattr(zealy_scraper, "run_scrape_once", None)
        or getattr(zealy_scraper, "run_once", None)
        or getattr(zealy_scraper, "scrape_once", None)
    )

    # As a last resort, if the scraper only exposes run_loop (which runs a continuous loop),
    # do NOT await it here (that would block); instead warn and skip.
    if not fn:
        # If run_loop exists we still don't call it here (it is a long-running loop)
        if getattr(zealy_scraper, "run_loop", None):
            logger.warning("Zealy scraper only exposes run_loop (continuous). Scheduler run_scraper_once will skip calling run_loop.")
        else:
            logger.warning("No callable scraper entrypoint found on zealy_scraper.")
        return []

    try:
        if asyncio.iscoroutinefunction(fn):
            return await fn(limit=limit)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(limit=limit))
    except Exception as e:
        logger.exception("Error when running scraper function from scheduler")
        return []

# ---------- Process DB ----------
async def process_unposted(bot: Any, max_items=5):
    sent = 0
    loop = asyncio.get_event_loop()
    for _ in range(max_items):
        airdrop = await loop.run_in_executor(None, get_unposted_airdrop)
        if not airdrop:
            break
        try:
            title = airdrop.get("title", "Untitled")
            link = airdrop.get("link")
            description = airdrop.get("description", "")
            twitter_url = airdrop.get("twitter_url", "")

            twitter_buzz = await loop.run_in_executor(None, lambda: rate_twitter_buzz(twitter_url)) if twitter_url else None
            scam_summary = await loop.run_in_executor(None, lambda: analyze_airdrop(title, description, link))

            if scam_summary and isinstance(scam_summary, dict) and scam_summary.get("score", 0) >= 30:
                logger.warning(f"⛔ Scam detected, skipping {title}")
                await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
                continue

            user_msg = format_user_message(airdrop)
            admin_msg = format_admin_message(airdrop, scam_summary, twitter_buzz)

            await send_airdrop_to_all(bot, title=title, description=user_msg, link=link, project=title)
            sent += 1

            admin_chat_id = int(os.getenv("ADMIN_CHAT_ID", "0"))
            if admin_chat_id:
                await bot.send_message(admin_chat_id, admin_msg, parse_mode="Markdown", disable_web_page_preview=False)

            await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
            logger.info(f"✅ Sent {title}")

        except Exception as e:
            logger.error(f"Error sending airdrop: {e}")
            await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
    return sent

# ---------- Scheduler ----------
def start_scheduler(bot: Any):
    logger.info("🚀 Starting scheduler...")
    scheduler = AsyncIOScheduler(timezone=utc)

    async def keep_alive():
        url = os.getenv("UPTIME_URL", "https://zkdrop-bot.onrender.com/uptime")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=10) as r:
                    logger.debug(f"Keep-alive {r.status}")
        except Exception as e:
            logger.debug(f"Keep-alive error {e}")

    async def live_job():
        logger.info("🔴 Live job running")
        await run_scraper_once(limit=25)
        await process_unposted(bot, max_items=8)

    async def interval_job():
        logger.info("🟠 Interval job running")
        await run_scraper_once(limit=40)
        await process_unposted(bot, max_items=12)

    async def daily_job():
        logger.info("🔵 Daily job running")
        await run_scraper_once(limit=50)
        await process_unposted(bot, max_items=25)

    scheduler.add_job(keep_alive, "interval", minutes=4, id="keep_alive")
    scheduler.add_job(live_job, "interval", seconds=60, id="live_job", max_instances=1)
    scheduler.add_job(interval_job, "interval", minutes=16, id="interval_job", max_instances=1)
    scheduler.add_job(daily_job, "cron", hour=DAILY_HOUR_UTC, minute=0, id="daily_job", max_instances=1)

    scheduler.start()
    logger.info("Scheduler jobs started: keep_alive, live(60s), interval(16m), daily")
    return scheduler
