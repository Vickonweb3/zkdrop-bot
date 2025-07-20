import asyncio
import logging
from utils.scraper import scrape_zealy_airdrops
from handlers.airdrop_notify import send_airdrop_to_all
from config.settings import TASK_INTERVAL_MINUTES

# ✅ the most annoying code with too much errors 
def start_scheduler(bot):
    logging.info("🚀 Starting background scheduler...")
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler(bot))

# 🔁 Background loop
async def run_scheduler(bot):
    while True:
        try:
            logging.info("🔄 Running background tasks...")

            try:
                # ⏰ Scrape new airdrops
                new_airdrops = scrape_zealy_airdrops()
            except Exception as scrape_err:
                logging.error(f"❌ Scraper Error: {scrape_err}")
                new_airdrops = []

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
