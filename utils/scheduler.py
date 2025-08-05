import asyncio
import logging
import aiohttp

from pytz import utc
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import TASK_INTERVAL_MINUTES
from database.db import get_unposted_airdrop, mark_airdrop_posted
from utils.twitter_rating import rate_twitter_buzz
from utils.scrapers.zealy import scrape_zealy
from utils.task.send_airdrop import send_airdrop_to_all
from utils.scam_analyzer import analyze_airdrop  # ✅ Added scam analyzer


def start_scheduler(bot):
    logging.info("🚀 Starting background scheduler...")
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler(bot))

    scheduler = AsyncIOScheduler(timezone=utc)

    async def keep_alive():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://zkdrop-bot.onrender.com/uptime") as resp:
                    if resp.status == 200:
                        logging.info("🟢 Keep-alive ping successful.")
                    else:
                        logging.warning(f"⚠️ Keep-alive ping failed with status: {resp.status}")
        except Exception as e:
            logging.error(f"❌ Keep-alive ping error: {e}")

    scheduler.add_job(keep_alive, "interval", minutes=4)
    scheduler.start()


async def run_scheduler(bot):
    while True:
        logging.info("🔄 Running Zealy scraper...")
        try:
            new_drops = scrape_zealy()
            logging.info(f"🔍 Found {len(new_drops)} new airdrops from Zealy.")
        except Exception as err:
            logging.error(f"❌ Zealy scrape error: {err}")

        try:
            airdrop = get_unposted_airdrop()
        except Exception as db_err:
            logging.error(f"❌ DB Error: {db_err}")
            airdrop = None

        if airdrop:
            try:
                # ✅ Scam analysis
                scam_score = analyze_airdrop(
                    link=airdrop["link"],
                    contract=airdrop.get("contract_address"),
                    token_symbol=airdrop.get("token_symbol")
                )
                if scam_score >= 30:
                    logging.warning(f"🚨 Scam score {scam_score} — Skipping {airdrop['title']}")
                    mark_airdrop_posted(airdrop["_id"])  # Still mark as posted to avoid loops
                    await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
                    continue

                # 🐦 Twitter Buzz Score
                try:
                    buzz_score = rate_twitter_buzz(airdrop.get("twitter_url", ""))
                    buzz_text = f"\n🔥 Twitter Buzz: {buzz_score}/10" if buzz_score else ""
                except Exception as buzz_err:
                    logging.warning(f"⚠️ Buzz rating failed: {buzz_err}")
                    buzz_text = ""

                # 📤 Send airdrop
                await send_airdrop_to_all(
                    bot,
                    title=airdrop.get("title", "Untitled"),
                    description=f"{airdrop.get('project_link', '')}\n{airdrop.get('twitter_url', '')}{buzz_text}",
                    link=airdrop["link"],
                    project=airdrop.get("project_name", "Unknown")
                )

                mark_airdrop_posted(airdrop["_id"])
                logging.info(f"✅ Airdrop sent: {airdrop['title']}")

            except Exception as err:
                logging.error(f"❌ Error sending airdrop: {err}")

        else:
            logging.info("😴 No pending airdrops to send.")

        await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
