import asyncio
import logging
import aiohttp

from config.settings import TASK_INTERVAL_MINUTES, ADMIN_ID
from database.db import get_unposted_airdrop, mark_airdrop_posted
from utils.twitter_rating import rate_twitter_buzz
from utils.scraper import scrape_zealy_airdrops  # ✅ New import

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ✅ Start the scheduler
def start_scheduler(bot):
    logging.info("🚀 Starting background scheduler...")
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler(bot))

    # ✅ Keep-alive job
    scheduler = AsyncIOScheduler()

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

# 🔁 Background task loop
async def run_scheduler(bot):
    while True:
        logging.info("🔄 Running Zealy scraper...")
        try:
            new_drops = scrape_zealy_airdrops()  # ✅ Run the scraper
            logging.info(f"🔍 Found {len(new_drops)} new airdrops from Zealy.")

            if not new_drops:
                logging.info("⚠️ No new drops scraped, checking DB for pending posts...")

        except Exception as err:
            logging.error(f"❌ Zealy scrape error: {err}")

        # ✅ Check Mongo for unposted airdrops
        try:
            airdrop = get_unposted_airdrop()
        except Exception as db_err:
            logging.error(f"❌ DB Error: {db_err}")
            airdrop = None

        if airdrop:
            try:
                # 🐦 Twitter Buzz
                try:
                    buzz_score = rate_twitter_buzz(airdrop.get("twitter_url", ""))
                    buzz_text = f"\n🔥 Twitter Buzz: {buzz_score}/10" if buzz_score else ""
                except Exception as buzz_err:
                    logging.warning(f"⚠️ Buzz rating failed: {buzz_err}")
                    buzz_text = ""

                # 🧾 Caption
                text = (
                    f"🚀 *New Airdrop Detected!*\n\n"
                    f"🔹 *Project:* {airdrop.get('project_name', 'Unknown')}\n"
                    f"🌐 *Website:* {airdrop.get('project_link', 'N/A')}\n"
                    f"🐦 *Twitter:* {airdrop.get('twitter_url', 'N/A')}"
                    f"{buzz_text}\n"
                    f"🔗 *Join Airdrop:* {airdrop['link']}"
                )

                await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")
                mark_airdrop_posted(airdrop["_id"])
                logging.info(f"✅ Airdrop posted: {airdrop['title']}")

            except Exception as err:
                logging.error(f"❌ Error sending airdrop: {err}")

        else:
            logging.info("😴 Nothing to post for now.")

        await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
