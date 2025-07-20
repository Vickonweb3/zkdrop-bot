import requests
from bs4 import BeautifulSoup
from datetime import datetime

def scrape_zealy_airdrops():
    url = "https://zealy.io/discover"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Check exact class by inspecting site — adjust if dynamic
        airdrop_elements = soup.find_all("div", class_="ProjectCard_root__")

        if not airdrop_elements:
            print("[⚠️ SCRAPER WARNING]: No airdrop elements found. Zealy layout may have changed.")
            return []

        scraped_data = []
        for el in airdrop_elements[:5]:
            name_tag = el.find("h3")
            anchor = el.find("a")

            name = name_tag.text.strip() if name_tag else "Unknown Project"
            link = anchor["href"] if anchor and "href" in anchor.attrs else "#"
            full_link = f"https://zealy.io{link}" if link.startswith("/") else link

            scraped_data.append({
                "title": f"{name} Quests",
                "description": f"Join {name}'s airdrop quests on Zealy now!",
                "link": full_link,
                "project": name
            })

        return scraped_data

    except requests.exceptions.RequestException as req_err:
        print(f"[❌ SCRAPER ERROR - Request]: {req_err}")
    except Exception as e:
        print(f"[❌ SCRAPER ERROR - General]: {e}")

    return []
