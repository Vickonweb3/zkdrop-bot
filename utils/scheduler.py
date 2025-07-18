import asyncio
from utils.scraper import scrape_zealy_airdrops
from handlers.airdrop_notify import send_airdrop_to_users
from config.settings import TASK_INTERVAL_MINUTES, SCRAPE_INTERVAL_HOURS
import logging

# 🧠 Background scheduler
def start_scheduler(bot):
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler(bot))

# 🔁 Main loop
async def run_scheduler(bot):
    while True:
        try:
            logging.info("🔄 Running background tasks...")

            # ⏰ Scrape new airdrops
            new_airdrops = await scrape_zealy_airdrops()

            # 📢 Send airdrops if found
            if new_airdrops:
                for drop in new_airdrops:
                    await send_airdrop_to_users(bot, drop)
            else:
                logging.info("⚠️ No new airdrops found.")

        except Exception as e:
            logging.error(f"🚨 Scheduler Error: {e}")

        # ⏱ Wait before running again
        await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
