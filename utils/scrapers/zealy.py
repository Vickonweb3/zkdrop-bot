# main/utils/scrapers/zealy.py
"""
Zealy scraper for zkDrop Bot (optimized for Render + anti-ban)
Updates:
- Secure MongoDB TLS (removed tlsAllowInvalidCertificates)
- Zealy rate limiting with random delays
- Randomized user-agents
- Fixed run_loop indentation bug
- Added connection timeouts
"""

import os
import json
import time
import math
import random  # NEW
import logging
import requests
from datetime import datetime, timedelta
from pymongo import MongoClient
from urllib.parse import urljoin

# Try to import dotenv if available (useful for local testing)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------------------- Configuration & Environment ----------------------
GRAPHQL_URL = "https://api.zealy.io/graphql"
HEADERS = {
    "content-type": "application/json",
    "user-agent": random.choice([  # NEW - Rotating user-agents
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (X11; Linux x86_64; rv:109.0)"
    ])
}

MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGO_URL") or os.getenv("DATABASE_URL")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "VickOnWeb3")

# Polling + daily schedule config
POLL_INTERVAL = int(os.getenv("ZEALY_POLL_INTERVAL", "60"))  # seconds between scrape passes
DAILY_HOUR_UTC = int(os.getenv("ZEALY_DAILY_HOUR_UTC", "9"))  # hour (0-23) for daily trending

# Validate minimal env
if not MONGO_URI:
    raise RuntimeError("MONGO_URI is required in env")
if not BOT_TOKEN:
    logging.warning("BOT_TOKEN not set. Sending will be skipped.")
if not ADMIN_ID:
    logging.warning("ADMIN_ID not set. Admin alerts will be skipped.")

# Convert ADMIN_ID to int if numeric
try:
    ADMIN_ID = int(ADMIN_ID)
except Exception:
    pass

# ---------------------- Logging ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------- MongoDB Setup ----------------------
mongo_client = MongoClient(  # NEW - Secure TLS config
    MONGO_URI,
    tls=True,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=10000
)
db = mongo_client.get_database("zkdrop_bot")
airdrops_col = db.get_collection("airdrops")
sent_log_col = db.get_collection("sent_log")
users_col = db.get_collection("users")

# ---------------------- External Helpers ----------------------
try:
    from utils.scam_analyzer import analyze_airdrop
except Exception:
    logging.warning("utils.scam_analyzer not found. Using fallback analyzer stub.")
    def analyze_airdrop(title, description, url):
        return {"score": 50, "verdict": "unknown", "details": {"note": "fallback analyzer used"}}

try:
    from utils.scam_filter import basic_scam_check
except Exception:
    try:
        from utils.scam_check import basic_scam_check
    except Exception:
        logging.warning("utils.scam_filter/basic_scam_check not found. Using fallback basic_scam_check.")
        def basic_scam_check(content):
            return {"is_scam": False, "flags": []}

try:
    from utils.twitter_rating import rate_twitter_buzz
except Exception:
    logging.info("utils.twitter_rating not found. Using fallback rate_twitter_buzz.")
    def rate_twitter_buzz(handle_or_url):
        return 50

# ---------------------- GraphQL Queries ----------------------
EXPLORE_QUERY = """
query ExploreCommunities($filter: String, $sort: Sort, $limit: Int, $offset: Int) {
  exploreCommunities(filter: $filter, sort: $sort, limit: $limit, offset: $offset) {
    name
    slug
    logo
    twitter
    createdAt
  }
}
"""

COMMUNITY_QUESTS_QUERY = """
query CommunityPage($slug: String!, $limit: Int) {
  community(slug: $slug) {
    name
    slug
    quests(limit: $limit) {
      title
      xp
      description
      claimLimit
      endsAt
    }
  }
}
"""

# ---------------------- Utility Functions ----------------------
def post_graphql(query, variables=None, timeout=12):
    """Send GraphQL POST with rate limiting."""  # NEW - Anti-ban delays
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    
    time.sleep(random.uniform(1.5, 3.5))  # NEW - Random delay
    
    try:
        resp = requests.post(
            GRAPHQL_URL,
            headers=HEADERS,
            json=payload,
            timeout=timeout
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logging.error(f"[GraphQL] request failed: {str(e)[:100]}...")
        return None

[... REST OF YOUR ORIGINAL FUNCTIONS REMAIN EXACTLY THE SAME ...]

# ---------------------- Runner / Scheduler ----------------------
def run_loop(poll_interval=POLL_INTERVAL, daily_hour=DAILY_HOUR_UTC):
    """Main loop with fixed indentation."""  # NEW - Fixed indentation bug
    logging.info("Zealy scraper started. Poll interval: %s seconds. Daily hour (UTC): %s", 
                poll_interval, daily_hour)
    last_daily_date = None
    
    while True:
        try:
            run_scrape_once(limit=25, sort="TRENDING")
            
            # Fixed indentation for daily trending:
            now = datetime.utcnow()
            today_date = now.date()
            if now.hour == daily_hour and (last_daily_date != today_date):
                try:
                    send_daily_trending(limit=12)
                    last_daily_date = today_date
                except Exception as e:
                    logging.error(f"Daily trending failed: {e}")
                    
        except Exception as e:
            logging.exception("Main scrape error")
            if ADMIN_ID:
                send_telegram_message(ADMIN_ID, f"[❌ Zealy main error] {str(e)[:200]}")

        time.sleep(poll_interval)

if __name__ == "__main__":
    run_loop()
