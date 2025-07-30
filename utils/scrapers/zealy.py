import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pymongo import MongoClient
from urllib.parse import urljoin
from telegram import Bot
from dotenv import load_dotenv

# 🔒 Load environment variables
load_dotenv(dotenv_path="resr/.env")

MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
VICK_CHAT_ID = int(os.getenv("ADMIN_ID"))
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# 🔌 Initialize MongoDB & Telegram Bot
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["zkdrop_bot"]
airdrops_col = db["airdrops"]
bot = Bot(token=TELEGRAM_TOKEN)

# 🔁 Check if airdrop already exists in DB
def is_duplicate(link):
    return airdrops_col.find_one({"link": link}) is not None

# 💾 Save new airdrop with full details
def save_airdrop(title, link, platform, score, twitter_url="N/A"):
    airdrops_col.insert_one({
        "title": title,
        "project_name": title.replace(" Quests", ""),
        "project_link": link,
        "twitter_url": twitter_url,
        "link": link,
        "platform": platform,
        "score": score,
        "timestamp": datetime.utcnow()
    })

# 🔎 Rate airdrop based on length + Twitter buzz
def rate_airdrop(name):
    score = 0
    if len(name) > 5:
        score += 20
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

# ✅ Scrape Zealy airdrops
def scrape_zealy_airdrops():
    url = "https://zealy.io/explore"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        soup = BeautifulSoup(res.text, "html.parser")

        cards = soup.select('div[class*="card"] a[href^="/c/"]')
        if not cards:
            bot.send_message(VICK_CHAT_ID, "⚠️ Zealy layout changed. Trying fallback...")
            return scrape_galxe_airdrops()

        new_drops = []
        seen_links = set()

        for card in cards[:10]:
            link = urljoin(url, card.get("href"))
            if link in seen_links or is_duplicate(link):
                continue
            seen_links.add(link)

            parent = card.find_parent("div")
            h3 = parent.find("h3") if parent else None
            if not h3:
                continue
            title = h3.text.strip()

            twitter_tag = parent.find("a", href=lambda h: h and ("twitter.com" in h or "x.com" in h))
            twitter_url = twitter_tag["href"] if twitter_tag else "N/A"

            score = rate_airdrop(title)
            save_airdrop(f"{title} Quests", link, "Zealy", score, twitter_url)

            new_drops.append({
                "title": f"{title} Quests",
                "description": f"Join {title} on Zealy — Score: {score}/100",
                "link": link,
                "score": score
            })

            bot.send_message(
                chat_id=VICK_CHAT_ID,
                text=f"🚀 *{title} Airdrop*\nScore: *{score}/100*\n🔗 {link}",
                parse_mode="Markdown"
            )

        return new_drops

    except Exception as e:
        bot.send_message(VICK_CHAT_ID, f"❌ Zealy scrape failed: {e}")
        return scrape_galxe_airdrops()

# 🛟 Fallback to Galxe (placeholder)
def scrape_galxe_airdrops():
    bot.send_message(VICK_CHAT_ID, "⚠️ Fallback to Galxe (not yet implemented).")
    return []

# 🔘 Manual run
if __name__ == "__main__":
    drops = scrape_zealy_airdrops()
    print(f"✅ {len(drops)} new airdrops scraped.")
