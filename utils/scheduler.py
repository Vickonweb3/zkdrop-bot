# 🔁 Background task loop
async def run_scheduler(bot):
    while True:
        logging.info("🔄 Running background tasks...")

        try:
            # ⏰ Scrape new airdrops
            # new_airdrops = scrape_zealy_airdrops()
            new_airdrops = []  # Disable scraper temporarily
        except Exception as scrape_err:
            logging.error(f"❌ Scraper Error: {scrape_err}")
            new_airdrops = []

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
                    logging.info(f"📤 Sent airdrop: {drop['title']}")
                except Exception as send_err:
                    logging.error(f"❌ Error sending airdrop: {send_err}")
        else:
            logging.info("⚠️ No new airdrops found.")

        # ⏳ Wait before next run
        await asyncio.sleep(TASK_INTERVAL_MINUTES * 60)
