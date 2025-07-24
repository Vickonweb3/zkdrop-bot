import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pymongo import MongoClient
from urllib.parse import urljoin
from telegram import Bot
from dotenv import load_dotenv

# Load .env file
load_dotenv(dotenv_path="resr/.env")

# Settings from .env
MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
VICK_CHAT_ID = int(os.getenv("ADMIN_ID"))
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")  # Optional for now

# Init MongoDB & Telegram bot
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["zkdrop_bot"]
airdrops_col = db["airdrops"]
bot = Bot(token=TELEGRAM_TOKEN)

# ✅ Check if airdrop already exists
def is_duplicate(link):
    return airdrops_col.find_one({"link": link}) is not None

# ✅ Save new airdrop with proper fields
def save_airdrop(title, link, platform, score):
    airdrops_col.insert_one({
        "title": title,
        "project_name": title.replace(" Quests", ""),  # remove suffix
        "project_link": link,
        "twitter_url": "N/A",  # Default placeholder, required by scheduler/snipe
        "link": link,
        "platform": platform,
        "score": score,
        "timestamp": datetime.utcnow()
    })

# ✅ Rate the airdrop using simple logic
def rate_airdrop(name):
    score = 0
    # Basic trust boost
    if len(name) > 5:
        score += 20

    # Twitter buzz logic (placeholder until full API)
    try:
        url = f"https://api.twitter.com/2/tweets/search/recent?query={name}"
        headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
        res = requests.get(url, headers=headers)
        data = res.json()
        if len(data.get("data", [])) > 20:
            score += 20
    except:
        score += 5

    return min(score, 100)

# ✅ Scrape Zealy
def scrape_zealy_airdrops():
    url = "https://zealy.io/discover"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        cards = soup.find_all("div", class_=lambda c: c and ("ProjectCard_root__" in c or "card" in c.lower()))
        if not cards:
            bot.send_message(chat_id=VICK_CHAT_ID, text="⚠️ Zealy layout may have changed! Trying fallback...")
            return []

        new_drops = []
        for card in cards[:5]:
            h3 = card.find("h3")
            anchor = card.find("a")
            if not h3 or not anchor:
                continue

            name = h3.text.strip()
            link = urljoin(url, anchor.get("href", "#"))

            if is_duplicate(link):
                continue

            score = rate_airdrop(name)
            save_airdrop(f"{name} Quests", link, "Zealy", score)

            new_drops.append({
                "title": f"{name} Quests",
                "description": f"Join {name} on Zealy — Score: {score}/100",
                "link": link,
                "score": score
            })

            # Optional: Send to you
            bot.send_message(
                chat_id=VICK_CHAT_ID,
                text=f"🚀 New Airdrop: *{name}*\nZealy Score: *{score}/100*\n👉 {link}",
                parse_mode="Markdown"
            )

        return new_drops

    except Exception as e:
        bot.send_message(chat_id=VICK_CHAT_ID, text=f"❌ Zealy scrape failed: {e}")
        return []

# ✅ Run scraper
if __name__ == "__main__":
    drops = scrape_zealy_airdrops()
    print(f"✅ {len(drops)} new airdrops scraped.")
