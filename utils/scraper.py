import requests
from bs4 import BeautifulSoup
from datetime import datetime

# 🌐 Scrape airdrop opportunities (default: Zealy for now)
def scrape_zealy_airdrops():
    url = "https://zealy.io/discover"  # Replace with real scraping target if needed
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # This is placeholder logic: Adjust based on actual HTML structure
        airdrop_elements = soup.find_all("div", class_="ProjectCard_root__")  # Example class

        scraped_data = []
        for el in airdrop_elements[:5]:  # Limit to first 5 entries for now
            name = el.find("h3").text.strip() if el.find("h3") else "Unknown Project"
            link = el.find("a")["href"] if el.find("a") else "#"
            date_scraped = datetime.utcnow().isoformat()

            scraped_data.append({
                "name": name,
                "link": link,
                "scraped_at": date_scraped
            })

        return scraped_data

    except Exception as e:
        print(f"[❌ SCRAPER ERROR]: {e}")
        return []
