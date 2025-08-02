import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pymongo import MongoClient
from telegram import Bot
from urllib.parse import urljoin

# 🔒 ENV variables (Render-ready)
MONGO_URI = os.getenv("MONGO_URI")
TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")
SCAM_API_KEY = os.getenv("SAFE_BROWSING_KEY")
SCAM_API_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

# 🔌 Setup
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["zkdrop_bot"]
airdrops_col = db["airdrops"]
bot = Bot(token=TELEGRAM_TOKEN)

# 📦 Check if already saved
def is_duplicate(link):
    return airdrops_col.find_one({"link": link}) is not None

# 🧠 Rate using Twitter Buzz
def rate_project(name):
    try:
        url = f"https://api.twitter.com/2/tweets/search/recent?query={name}"
        headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
        res = requests.get(url, headers=headers)
        data = res.json()
        return min(len(data.get("data", [])) * 5, 100)
    except:
        return 15

# 🛡 Scam Detection
def is_scam(link, description):
    payload = {
        "client": {"clientId": "zkdrop-bot", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": link}],
        },
    }
    try:
        resp = requests.post(f"{SCAM_API_URL}?key={SCAM_API_KEY}", json=payload, timeout=10)
        if resp.json().get("matches"):
            return True
        # Basic keyword scan (backup)
        scam_words = ["airdrop soon", "free now", "double your", "claim fast", "airdropsoon", "urgent reward"]
        return any(word.lower() in description.lower() for word in scam_words)
    except:
        return False

# 💾 Store in DB
def save_airdrop(title, link, platform, score, twitter_url="N/A", xp="Unknown", description=""):
    airdrops_col.insert_one({
        "title": title,
        "project_name": title.replace(" Quests", ""),
        "project_link": link,
        "twitter_url": twitter_url,
        "link": link,
        "platform": platform,
        "score": score,
        "xp": xp,
        "description": description,
        "timestamp": datetime.utcnow()
    })

# 🔍 Scrape Zealy
def scrape_zealy():
    url = "https://zealy.io/explore"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.select('div[class*="card"] a[href^="/c/"]')

        if not cards:
            bot.send_message(ADMIN_ID, "⚠️ Zealy layout changed. No cards found.")
            return []

        new_drops = []
        seen = set()

        for card in cards[:15]:
            link = urljoin(url, card.get("href"))
            if link in seen or is_duplicate(link):
                continue
            seen.add(link)

            parent = card.find_parent("div")
            h3 = parent.find("h3") if parent else None
            if not h3:
                continue
            title = h3.text.strip()

            # Get XP
            xp_span = parent.find("span")
            xp = xp_span.text.strip().replace("XP", "") if xp_span else "0"
            try:
                xp_int = int(xp.replace("K", "000").replace(",", "").strip())
            except:
                xp_int = 9999
            if xp_int > 100:
                continue

            # Get Twitter
            twitter_tag = parent.find("a", href=lambda h: h and ("twitter.com" in h or "x.com" in h))
            twitter_url = twitter_tag["href"] if twitter_tag else "N/A"

            # Get Description
            desc_tag = parent.find("p")
            description = desc_tag.text.strip() if desc_tag else "No description."

            score = rate_project(title)

            if is_scam(link, description):
                bot.send_message(ADMIN_ID, f"🚨 Scam project skipped: {title}")
                continue

            save_airdrop(f"{title} Quests", link, "Zealy", score, twitter_url, xp, description)

            # 📬 Telegram message
            rank_tag = "🔥 *Top Rank!*" if score >= 100 else ""
            message = (
                f"🚀 *{title}*\n"
                f"{rank_tag}\n\n"
                f"📖 *What is it?*\n_{description}_\n\n"
                f"🎯 *XP:* {xp}\n"
                f"📊 *Buzz Score:* {score}/100\n"
                f"🐦 *Twitter:* {twitter_url}\n"
                f"🔗 *Join Now:* {link}"
            )

            bot.send_message(chat_id=ADMIN_ID, text=message, parse_mode="Markdown")
            new_drops.append(link)

        return new_drops

    except Exception as e:
        bot.send_message(ADMIN_ID, f"❌ Error scraping Zealy: {e}")
        return []

# 🔁 Auto-run every 60s
if __name__ == "__main__":
    print("⏳ Zealy monitor running...")
    while True:
        try:
            drops = scrape_zealy()
            print(f"✅ {len(drops)} new airdrops")
        except Exception as err:
            print(f"❌ Error: {err}")
        time.sleep(60)
