# utils/scheduler.py
import asyncio
import logging
import traceback
from datetime import datetime
from typing import Any, List, Optional

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import utc

from config.settings import TASK_INTERVAL_MINUTES, DAILY_HOUR_UTC
from database.db import get_unposted_airdrop, mark_airdrop_posted, log_airdrop_sent  # log_airdrop_sent optional
from utils.task.send_airdrop import send_airdrop_to_all
from utils.scam_analyzer import analyze_airdrop
from utils.twitter_rating import rate_twitter_buzz

# Attempt to import the zealy scraper module (supports multiple variants)
try:
    from utils.scrapers import zealy as zealy_scraper
except Exception:
    zealy_scraper = None

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ---------- Helper: format messages ----------
def format_user_message(airdrop):
    """Format message for regular users"""
    title = airdrop.get('title', 'Unknown')
    xp = airdrop.get('xp', 'N/A')
    description = airdrop.get('description', 'No description')
    link = airdrop.get('link', '#')
    
    # Truncate description if too long
    if len(description) > 120:
        description = description[:120] + "..."
    
    return (
        f"🚀 **New Airdrop Alert!** 🚀\n\n"
        f"🔹 **{title}**\n"
        f"💎 XP: {xp}\n\n"
        f"📖 {description}\n\n"
        f"👉 [Join Airdrop]({link})"
    )

def format_admin_message(airdrop, scam_summary=None, twitter_buzz=None):
    """Format detailed message for admin"""
    title = airdrop.get('title', 'Unknown')
    xp = airdrop.get('xp', 'N/A')
    description = airdrop.get('description', 'No description')
    link = airdrop.get('link', '#')
    
    scam_status = "Not checked"
    if scam_summary:
        scam_score = scam_summary.get('score', 'N/A')
        scam_verdict = scam_summary.get('verdict', 'unknown')
        scam_status = f"Score: {scam_score}, Verdict: {scam_verdict}"
    
    buzz_info = f"Twitter Buzz: {twitter_buzz}" if twitter_buzz else "Twitter: Not available"
    
    return (
        f"📢 **New Airdrop Detected**\n\n"
        f"🔹 **Title:** {title}\n"
        f"💎 **XP:** {xp}\n"
        f"📖 **Description:** {description}\n"
        f"🔗 **Link:** {link}\n"
        f"🕒 **Detected:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"⚠️ **Scam Check:** {scam_status}\n"
        f"🔥 **{buzz_info}**"
    )


# ---------- Helper: call scraper (async-aware) ----------
async def run_scraper_once(limit: int = 25, sort: str = "TRENDING") -> List[dict]:
    """
    Try to call an async scraper function if available, otherwise fall back to sync function
    executed in a thread executor. Returns list of communities/airdrops (dicts).
    Expected dict keys: at minimum a 'link' and 'title' (other fields optional).
    """
    if zealy_scraper is None:
        logger.warning("Zealy scraper module not available (utils.scrapers.zealy). Returning empty list.")
        return []

    # Preferred async function names (common in our codebase)
    async_names = ["run_scrape_once", "fetch_explore_communities", "run_once", "fetch_communities"]
    for name in async_names:
        fn = getattr(zealy_scraper, name, None)
        if fn and asyncio.iscoroutinefunction(fn):
            try:
                logger.debug(f"Calling async scraper function: {name}()")
                return await fn(limit=limit) if "limit" in fn.__code__.co_varnames else await fn()
            except Exception as e:
                logger.exception(f"Async scraper {name} failed: {e}")
                return []

    # Preferred sync function names (fall back to running in threadpool)
    sync_names = ["run_scrape_once", "run_once", "scrape_once", "scrape_zealy"]
    loop = asyncio.get_event_loop()
    for name in sync_names:
        fn = getattr(zealy_scraper, name, None)
        if fn and not asyncio.iscoroutinefunction(fn):
            try:
                logger.debug(f"Calling sync scraper function in executor: {name}()")
                return await loop.run_in_executor(None, lambda: fn(limit=limit) if "limit" in fn.__code__.co_varnames else fn())
            except Exception as e:
                logger.exception(f"Sync scraper {name} failed (executor): {e}")
                return []

    logger.warning("No matching scraper function found on utils.scrapers.zealy")
    return []


# ---------- Helper: process DB unposted airdrops ----------
async def process_unposted_airdrops(bot: Any, max_items: int = 5):
    """
    Fetch up to `max_items` unposted airdrops from DB (using get_unposted_airdrop)
    and send them to users via send_airdrop_to_all. Marks as posted afterwards.
    This function expects `get_unposted_airdrop()` to return one airdrop doc or None.
    """
    sent_count = 0
    for _ in range(max_items):
        try:
            airdrop = None
            # DB call is synchronous in many setups - run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            airdrop = await loop.run_in_executor(None, get_unposted_airdrop)
        except Exception as e:
            logger.exception(f"DB retrieval failed: {e}")
            break

        if not airdrop:
            break

        try:
            title = airdrop.get("title", "Untitled")
            link = airdrop.get("link")
            xp = airdrop.get("xp", "N/A")
            description = airdrop.get("description", "") or ""
            twitter_url = airdrop.get("twitter_url", "") or ""
            
            # Twitter buzz (run in executor if sync)
            twitter_buzz = None
            try:
                loop = asyncio.get_event_loop()
                twitter_buzz = await loop.run_in_executor(None, lambda: rate_twitter_buzz(twitter_url) if twitter_url else None)
            except Exception:
                logger.debug("Twitter rating failed for airdrop", exc_info=True)

            # Scam check (run in executor if sync)
            scam_summary = {}
            try:
                loop = asyncio.get_event_loop()
                scam_summary = await loop.run_in_executor(None, lambda: analyze_airdrop(title, description, link))
            except Exception:
                logger.debug("Scam analyzer failed", exc_info=True)
                scam_summary = {"score": None, "verdict": "unknown"}

            # If scam score present and too high, skip sending but still mark posted to avoid loops
            try:
                scam_score = scam_summary.get("score") if isinstance(scam_summary, dict) else None
                if scam_score is not None and isinstance(scam_score, (int, float)) and scam_score >= 30:
                    logger.warning(f"Skipping {title} due to high scam score: {scam_score}")
                    # mark posted (run in executor to avoid blocking)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
                    continue
            except Exception:
                logger.debug("Error evaluating scam score", exc_info=True)

            # Format messages using new format
            user_message = format_user_message(airdrop)
            admin_message = format_admin_message(airdrop, scam_summary, twitter_buzz)

            # Send to users (async function)
            try:
                # Assuming send_airdrop_to_all can handle formatted messages
                # You might need to modify send_airdrop_to_all to accept pre-formatted text
                await send_airdrop_to_all(
                    bot,
                    title=title,
                    description=user_message,  # Pass formatted message
                    link=link,
                    project=title  # Using title as project name
                )
                sent_count += 1
                logger.info(f"Sent airdrop: {title}")
                
                # Also send admin notification (optional)
                try:
                    admin_chat_id = int(os.getenv("ADMIN_CHAT_ID", 0))
                    if admin_chat_id:
                        await bot.send_message(
                            chat_id=admin_chat_id,
                            text=admin_message,
                            parse_mode="Markdown",
                            disable_web_page_preview=False
                        )
                except Exception as e:
                    logger.debug(f"Failed to send admin notification: {e}")
                    
            except Exception as e:
                logger.exception(f"Failed to send airdrop to users: {e}")

            # Mark posted (safe: run in executor)
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
            except Exception:
                logger.exception("Failed to mark airdrop posted in DB")

        except Exception as e:
            logger.exception(f"Error processing airdrop record: {e}")
            # Avoid tight loop on poison records — mark as posted to skip later
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
            except Exception:
                pass

    return sent_count


# ---------- Jobs ----------
def start_scheduler(bot: Any):
    """
    Initialize and start the AsyncIOScheduler with all required background jobs.
    Pass your bot instance (telegram bot) so send functions can use it.
    """
    logger.info("🚀 Starting scheduler...")
    scheduler = AsyncIOScheduler(timezone=utc)

    # ---- keep-alive job (every 4 minutes) ----
    async def keep_alive():
        uptime_url = os.getenv("UPTIME_URL") or "https://zkdrop-bot.onrender.com/uptime"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(uptime_url, timeout=10) as resp:
                    if resp.status == 200:
                        logger.debug("Keep-alive ping OK")
                    else:
                        logger.warning(f"Keep-alive ping returned status {resp.status}")
        except Exception as e:
            logger.debug(f"Keep-alive ping error: {e}")

    scheduler.add_job(keep_alive, "interval", minutes=4, id="keep_alive")

    # ---- live job (real-time) ----
    async def live_job():
        logger.info("🔴 [live_job] Running live scrape + process unposted")
        try:
            # Run a scrape pass (this may populate DB via other parts of your system)
            scraped = await run_scraper_once(limit=25)
            logger.info(f"[live_job] Scraper returned {len(scraped)} items")
        except Exception:
            logger.exception("Scraper in live_job failed")

        # Process unposted items saved in DB (send them out)
        try:
            sent = await process_unposted_airdrops(bot, max_items=8)
            logger.info(f"[live_job] Sent {sent} airdrops from DB")
        except Exception:
            logger.exception("Processing unposted airdrops failed in live_job")

    scheduler.add_job(live_job, "interval", seconds=60, id="live_job", max_instances=1)

    # ---- interval job (every 16 minutes) ----
    async def interval_job():
        logger.info("🟠 [interval_job] Running scrape (16min) + process unposted")
        try:
            scraped = await run_scraper_once(limit=40)
            logger.info(f"[interval_job] Scraper returned {len(scraped)} items")
        except Exception:
            logger.exception("Scraper in interval_job failed")

        try:
            sent = await process_unposted_airdrops(bot, max_items=12)
            logger.info(f"[interval_job] Sent {sent} airdrops from DB")
        except Exception:
            logger.exception("Processing unposted airdrops failed in interval_job")

    scheduler.add_job(interval_job, "interval", minutes=16, id="interval_job", max_instances=1)

    # ---- daily trending job (once per day at configured UTC hour) ----
    async def daily_job():
        logger.info("🔵 [daily_job] Running daily trending")
        try:
            # run a scrape pass for trending - larger limit
            scraped = await run_scraper_once(limit=50)
            logger.info(f"[daily_job] Scraper returned {len(scraped)} items")
        except Exception:
            logger.exception("Scraper in daily_job failed")

        try:
            # Process more items for daily send
            sent = await process_unposted_airdrops(bot, max_items=25)
            logger.info(f"[daily_job] Sent {sent} airdrops from DB (daily)")
        except Exception:
            logger.exception("Processing unposted airdrops failed in daily_job")

    # schedule daily at configured hour (UTC)
    scheduler.add_job(daily_job, "cron", hour=DAILY_HOUR_UTC, minute=0, id="daily_job", max_instances=1)

    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started with jobs: keep_alive, live_job (60s), interval_job (16m), daily_job (daily)")

    return scheduler


# If you want to run a standalone test run (not used by production), you can run:
if __name__ == "__main__":
    import os
    from types import SimpleNamespace

    # Create dummy bot object with required API if you want to test locally
    class DummyBot:
        pass

    bot = DummyBot()
    logger.info("Starting scheduler (standalone test)")
    sched = start_scheduler(bot)
    try:
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        logger.info("Scheduler stopped by user")
