# utils/scheduler.py
import os
import asyncio
import logging
from datetime import datetime
from typing import Any, List

import aiohttp
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pytz import utc

from config.settings import TASK_INTERVAL_MINUTES, DAILY_HOUR_UTC, ADMIN_ID
from database.db import get_unposted_airdrop, mark_airdrop_posted, get_all_users
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
        f"🚀 *New Airdrop Alert!* \n\n"
        f"🔹 *{title}*\n"
        f"💎 *XP:* {xp}\n\n"
        f"📖 {description}\n\n"
        f"👉 [Join Airdrop]({link})\n\n"
        f"✨ Good luck! Stay safe and don't share private keys."
    )

def format_admin_message_for_item(airdrop: dict, scam_summary=None, twitter_buzz=None) -> str:
    # A detailed admin report for a single airdrop/item
    title = airdrop.get("title", "Unknown")
    xp = airdrop.get("xp", "N/A")
    description = airdrop.get("description", "No description")
    link = airdrop.get("link", "#")
    scam_text = "Not checked"
    if scam_summary:
        scam_text = f"Score: {scam_summary.get('score')} — Verdict: {scam_summary.get('verdict')}"
    buzz_text = f"{twitter_buzz}" if twitter_buzz else "N/A"
    return (
        f"📢 *New Airdrop Detected (Admin Report)*\n\n"
        f"*Title:* {title}\n"
        f"*XP:* {xp}\n"
        f"*Link:* {link}\n"
        f"*Detected:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"*Scam Check:* {scam_text}\n"
        f"*Twitter Buzz Score:* {buzz_text}\n\n"
        f"📄 Description:\n{description[:400]}"
    )

def format_admin_daily_report(digest_message: str, sent_count: int) -> str:
    # Admin report for the daily digest run (sent_count = number of users the digest was broadcast to)
    return (
        f"📊 *Daily Trending Airdrops Report*\n\n"
        f"*When:* {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
        f"*Broadcasted to:* {sent_count} users\n\n"
        f"{digest_message[:4000]}\n\n"
        f"🔔 Note: Full digest was also broadcast to all users."
    )

# ---------- Scraper wrapper used by scheduler ----------
async def run_scraper_once(limit=25) -> List[dict]:
    """
    Call the scraper's single-run function. The zealy scraper in this repo exposes
    run_scrape_once(limit=...) — check for that first. Fall back to run_once/scrape_once
    if present. If only a continuous run_loop exists, do NOT call it from here (it would block).
    Returns whatever the scraper returns (or [] if none).
    """
    if not zealy_scraper:
        logger.warning("No Zealy scraper module found.")
        return []

    fn = (
        getattr(zealy_scraper, "run_scrape_once", None)
        or getattr(zealy_scraper, "run_once", None)
        or getattr(zealy_scraper, "scrape_once", None)
    )

    if not fn:
        # If only run_loop exists, scheduler should not call it here
        if getattr(zealy_scraper, "run_loop", None):
            logger.debug("Zealy scraper exposes run_loop (continuous). Scheduler run_scraper_once will skip calling run_loop.")
        else:
            logger.debug("No usable run-once function found on zealy_scraper.")
        return []

    try:
        if asyncio.iscoroutinefunction(fn):
            return await fn(limit=limit)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(limit=limit))
    except Exception as e:
        logger.exception("Error when running scraper function from scheduler")
        return []

# ---------- Process DB & broadcast ----------
async def process_unposted(bot: Any, max_items=5):
    """
    Pull up to max_items unposted airdrops from DB and broadcast them.
    For each item: run twitter rating & scam checks, send user-friendly message to all users,
    send admin detailed report to ADMIN_ID, then mark posted.
    """
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

            # If the analyzer flags it as high-scam score, we skip sending to users but still mark posted and notify admin
            if scam_summary and isinstance(scam_summary, dict) and scam_summary.get("score", 0) >= 30:
                logger.warning(f"⛔ Scam detected, skipping user broadcast for {title}")
                # Still inform admin about skipped item
                admin_msg_skip = format_admin_message_for_item(airdrop, scam_summary=scam_summary, twitter_buzz=twitter_buzz)
                if ADMIN_ID:
                    try:
                        await bot.send_message(ADMIN_ID, admin_msg_skip, parse_mode="Markdown", disable_web_page_preview=False)
                    except Exception:
                        logger.exception("Failed to send admin message for skipped scam item")
                await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
                continue

            user_msg = format_user_message(airdrop)
            admin_msg = format_admin_message_for_item(airdrop, scam_summary, twitter_buzz)

            # Send user-friendly message to all users
            await send_airdrop_to_all(bot, title=title, description=user_msg, link=link, project=title, preformatted=True)
            sent += 1

            # Send a detailed admin report (if ADMIN_ID set)
            if ADMIN_ID:
                try:
                    await bot.send_message(ADMIN_ID, admin_msg, parse_mode="Markdown", disable_web_page_preview=False)
                except Exception:
                    logger.exception("Failed to send admin message for item")

            await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
            logger.info(f"✅ Sent {title}")

        except Exception as e:
            logger.error(f"Error sending airdrop: {e}")
            try:
                await loop.run_in_executor(None, lambda: mark_airdrop_posted(airdrop["_id"]))
            except Exception:
                logger.exception("Failed to mark airdrop posted after error")
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
        # First run scraper to ensure DB is fresh
        await run_scraper_once(limit=50)

        # Build daily digest via scraper's helper (if available)
        digest = None
        try:
            if zealy_scraper and getattr(zealy_scraper, "send_daily_trending", None):
                # We ask the scraper to return the digest string but not send to admin (scheduler will handle admin + broadcast)
                digest = await zealy_scraper.send_daily_trending(limit=12, send_to_admin=False)
        except Exception:
            logger.exception("Error while building daily digest from scraper")

        # If we have a digest, send admin report first then broadcast to all users
        if digest:
            # Build admin report (short) and send to ADMIN_ID
            try:
                # get count of users
                user_count = 0
                try:
                    users = get_all_users()
                    user_count = len(users) if users else 0
                except Exception:
                    logger.debug("Could not fetch user count for admin report")

                admin_report = format_admin_daily_report(digest, sent_count=user_count)
                if ADMIN_ID:
                    await bot.send_message(ADMIN_ID, admin_report, parse_mode="Markdown", disable_web_page_preview=False)
            except Exception:
                logger.exception("Failed to send admin daily report")

            # Broadcast the digest to all users (preformatted message)
            try:
                await send_airdrop_to_all(bot, title="Daily Trending Airdrops Digest", description=digest, link="", project="Trending", preformatted=True)
            except Exception:
                logger.exception("Failed to broadcast daily digest to users")

        # Finally, also process any unposted items individually
        await process_unposted(bot, max_items=25)

    # Add scheduler jobs
    scheduler.add_job(keep_alive, "interval", minutes=4, id="keep_alive")
    scheduler.add_job(live_job, "interval", seconds=60, id="live_job", max_instances=1)
    scheduler.add_job(interval_job, "interval", minutes=16, id="interval_job", max_instances=1)
    scheduler.add_job(daily_job, "cron", hour=DAILY_HOUR_UTC, minute=0, id="daily_job", max_instances=1)

    scheduler.start()
    logger.info("Scheduler jobs started: keep_alive, live(60s), interval(16m), daily")
    return scheduler
