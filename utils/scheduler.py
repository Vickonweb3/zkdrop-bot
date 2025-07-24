import asyncio
import logging

from config.settings import TASK_INTERVAL_MINUTES, ADMIN_ID
from database.db import get_unposted_airdrop, mark_airdrop_posted
from utils.twitter_rating import rate_twitter_buzz
from utils.send_to_community import send_airdrop_to_main_group

# ✅ Function to start scheduler
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
            logging.error(f"❌ Database Error: {db_err}")
            airdrop = None

        if airdrop:
            try:
                # ⭐️ Get Twitter rating
                buzz_score = rate_twitter_buzz(airdrop["link"])
                buzz_text = f"\n🔥 Twitter Buzz: {buzz_score}/10" if buzz_score else ""

                # 📢 Format message
                text = (
                    f"🪂 *New Airdrop on {airdrop['platform']}*\n\n"
                    f"📌 {airdrop['title']}\n"
                    f"🔗 {airdrop['link']}"
                    f"{buzz_text}"
                )

                # 📤 Send to bot (your DM)
                await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")

                # ✅ Mark as posted
                mark_airdrop_posted(airdrop["link"])
                logging.info(f"📤 Airdrop posted: {airdrop['title']}")

            except Exception as err:
                logging.error(f"❌ Error posting airdrop: {err}")
        else:
            logging.info("⚠️ No new unposted airdrops.")

        await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
