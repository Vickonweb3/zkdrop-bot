import aiohttp
import logging
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

ZEEK_BASE_URL = "https://zealy.io"

# ⏱ Set your scraping interval here
SCRAPE_INTERVAL_MINUTES = 16

# 🚀 Scrape Zealy for new or top airdrops
async def scrape_zealy_airdrops():
    airdrops = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ZEEK_BASE_URL}/explore") as response:
                if response.status != 200:
                    logging.warning("⚠️ Zealy returned non-200 status.")
                    return []

                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")
                projects = soup.select("a[href^='/c/']")

                now = datetime.utcnow()
                threshold_time = now - timedelta(minutes=SCRAPE_INTERVAL_MINUTES)

                for tag in projects:
                    href = tag['href']
                    project_name = tag.text.strip()
                    full_url = f"{ZEEK_BASE_URL}{href}"

                    if not project_name:
                        continue

                    # 🕒 Try to extract time-based logic (Zealy doesn't show post time clearly)
                    # So here we assume first few are most recent (for now)
                    airdrops.append({
                        "name": project_name,
                        "url": full_url,
                        "added_time": now  # Simulate current time as posted time (Zealy doesn't provide real time)
                    })

                # ⚙️ Filter for new airdrops
                new_airdrops = [
                    a for a in airdrops
                    if a["added_time"] > threshold_time
                ]

                if new_airdrops:
                    return new_airdrops
                else:
                    # 🧼 Return top 3 if no fresh one
                    return airdrops[:3]

    except Exception as e:
        logging.error(f"❌ Zealy scraping error: {e}")
        return []
