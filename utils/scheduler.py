import asyncio
import logging

from config.settings import TASK_INTERVAL_MINUTES, ADMIN_ID
from database.db import get_unposted_airdrop, mark_airdrop_posted
from utils.twitter_rating import rate_twitter_buzz

# ✅ Start the scheduler
def start_scheduler(bot):
    logging.info("🚀 Starting background scheduler...")
    loop = asyncio.get_event_loop()
    loop.create_task(run_scheduler(bot))

# 🔁 Background task loop
async def run_scheduler(bot):
    while True:
        logging.info("🔄 Checking for new airdrops...")

        try:
            airdrop = get_unposted_airdrop()
        except Exception as db_err:
            logging.error(f"❌ DB Error: {db_err}")
            airdrop = None

        if airdrop:
            try:
                # 🐦 Rate Twitter buzz (safely)
                try:
                    buzz_score = rate_twitter_buzz(airdrop.get("twitter_url", ""))
                    buzz_text = f"\n🔥 Twitter Buzz: {buzz_score}/10" if buzz_score else ""
                except Exception as buzz_err:
                    logging.warning(f"⚠️ Buzz rating failed: {buzz_err}")
                    buzz_text = ""

                # 🧾 Prepare caption
                text = (
                    f"🚀 *New Airdrop Detected!*\n\n"
                    f"🔹 *Project:* {airdrop.get('project_name', 'Unknown')}\n"
                    f"🌐 *Website:* {airdrop.get('project_link', 'N/A')}\n"
                    f"🐦 *Twitter:* {airdrop.get('twitter_url', 'N/A')}"
                    f"{buzz_text}\n"
                    f"🔗 *Join Airdrop:* {airdrop['link']}"
                )

                # 📤 Send to bot admin
                await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")

                # ✅ Mark as posted
                mark_airdrop_posted(airdrop["_id"])
                logging.info(f"✅ Airdrop posted: {airdrop['title']}")

            except Exception as err:
                logging.error(f"❌ Error sending airdrop: {err}")

        else:
            logging.info("⚠️ No new unposted airdrops found.")

        await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
