import asyncio
from utils.scraper import scrape_zealy_airdrops
from handlers.airdrop_notify import send_airdrop_to_all
from config.settings import TASK_INTERVAL_MINUTES
import logging

# 🧠 Background scheduler
def start_scheduler(bot):
    logging.info("🚀 Starting background scheduler...")
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler(bot))

# 🔁 Main loop
async def run_scheduler(bot):
    while True:
        try:
            logging.info("🔄 Running background tasks...")

            # ⏰ Scrape new airdrops
            new_airdrops = scrape_zealy_airdrops()

            # 📢 Send airdrops if found
            if new_airdrops:
                for drop in new_airdrops:
                    try:
                        await send_airdrop_to_all(
                            bot,
                            drop["title"],
                            drop["description"],
                            drop["link"],
                            drop["project"]
                        )
                    except Exception as send_err:
                        logging.error(f"❌ Error sending airdrop: {send_err}")
            else:
                logging.info("⚠️ No new airdrops found.")

        except Exception as e:
            logging.error(f"🚨 Scheduler Error: {e}")

        await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
