import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 🌐 Scrape airdrop opportunities (default: Zealy for now)
def scrape_zealy_airdrops():
    url = "https://zealy.io/discover"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # ⚠️ Adjust class name as needed based on actual Zealy structure
        airdrop_elements = soup.find_all("div", class_="ProjectCard_root__")

        scraped_data = []
        for el in airdrop_elements[:5]:  # Limit to first 5 entries
            name = el.find("h3").text.strip() if el.find("h3") else "Unknown Project"
            anchor = el.find("a")
            link = anchor["href"] if anchor and "href" in anchor.attrs else "#"
            full_link = f"https://zealy.io{link}" if link.startswith("/") else link

            scraped_data.append({
                "title": f"{name} Quests",
                "description": f"Join {name}'s airdrop quests on Zealy now!",
                "link": full_link,
                "project": name
            })

        return scraped_data

    except Exception as e:
        print(f"[❌ SCRAPER ERROR]: {e}")
        return []
