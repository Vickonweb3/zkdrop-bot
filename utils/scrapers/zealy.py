import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from pymongo import MongoClient

from utils.twitter_rating import rate_project
from utils.scam_analyzer import is_scam

MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = client["zkdrop_bot"]
airdrops_col = db["airdrops"]

def is_duplicate(link):
    return airdrops_col.find_one({"link": link}) is not None

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

def scrape_zealy():
    url = "https://zealy.io/explore"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")
        cards = soup.select('div[class*="card"] a[href^="/c/"]')

        if not cards:
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

            xp_span = parent.find("span")
            xp = xp_span.text.strip().replace("XP", "") if xp_span else "0"
            try:
                xp_int = int(xp.replace("K", "000").replace(",", "").strip())
            except:
                xp_int = 9999
            if xp_int > 100:
                continue

            twitter_tag = parent.find("a", href=lambda h: h and ("twitter.com" in h or "x.com" in h))
            twitter_url = twitter_tag["href"] if twitter_tag else "N/A"

            desc_tag = parent.find("p")
            description = desc_tag.text.strip() if desc_tag else "No description."

            score = rate_project(title)

            if is_scam(link, description):
                continue

            save_airdrop(f"{title} Quests", link, "Zealy", score, twitter_url, xp, description)

            message = (
                f"🚀 *{title}*\n"
                f"🎯 *XP:* {xp}\n"
                f"📊 *Buzz Score:* {score}/100\n"
                f"🐦 *Twitter:* {twitter_url}\n"
                f"🔗 *Join Now:* {link}"
            )

            new_drops.append({
                "link": link,
                "title": title,
                "message": message
            })

        return new_drops

    except Exception as e:
        print(f"[❌ Zealy Scraper Error] {e}")
        return []
