import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pymongo import MongoClient
from urllib.parse import urljoin
from config.settings import MONGO_URI

client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["zkdrop_bot"]
airdrops_collection = db["airdrops"]

# ✅ Check if airdrop already exists
def is_duplicate(link):
    return airdrops_collection.find_one({"link": link}) is not None

# ✅ Save new airdrop
def save_airdrop(data):
    data["timestamp"] = datetime.utcnow()
    airdrops_collection.insert_one(data)

# 🔧 Rate airdrop placeholder (we’ll improve later)
def rate_airdrop(link, name):
    return 0  # Placeholder score

# 🚀 Main Zealy scraper
def scrape_zealy_airdrops():
    url = "https://zealy.io/discover"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        cards = soup.find_all("div", class_=lambda c: c and ("ProjectCard" in c or "card" in c.lower()))
        if not cards:
            print("⚠️ Zealy structure may have changed.")
            return scrape_galxe_airdrops()  # fallback

        new_drops = []
        for card in cards[:10]:
            title_tag = card.find("h3")
            link_tag = card.find("a")
            if not title_tag or not link_tag:
                continue

            name = title_tag.text.strip()
            href = link_tag.get("href", "#")
            link = urljoin(url, href)

            if is_duplicate(link):
                continue

            score = rate_airdrop(link, name)
            airdrop = {
                "title": f"{name} Quests",
                "description": f"Join {name} on Zealy! Score: {score}/100",
                "link": link,
                "platform": "Zealy",
                "project": name,
                "score": score
            }

            save_airdrop(airdrop)
            new_drops.append(airdrop)

        return new_drops

    except Exception as e:
        print(f"❌ Zealy scrape error: {e}")
        return scrape_galxe_airdrops()  # fallback

# 🌌 Fallback placeholder
def scrape_galxe_airdrops():
    print("🔄 Switching to Galxe fallback...")
    return []
