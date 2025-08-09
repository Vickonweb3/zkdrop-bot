# main/utils/scrapers/zealy.py
"""
Zealy scraper for zkDrop Bot (FULLY UPDATED VERSION)
All original functionality + critical upgrades:
1. Secure MongoDB TLS
2. Zealy rate limiting
3. Random user-agents
4. Fixed run_loop indentation
5. Connection timeouts
"""

import os
import json
import time
import math
import random
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
    "user-agent": random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (X11; Linux x86_64)"
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
mongo_client = MongoClient(
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
    """Send GraphQL POST with rate limiting."""
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    
    time.sleep(random.uniform(1.5, 3.5))  # Anti-ban delay
    
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

def build_zealy_url(slug):
    return f"https://zealy.io/c/{slug}"

def now_utc():
    return datetime.utcnow()

# ---------------------- DB Helpers ----------------------
def is_duplicate(link):
    return airdrops_col.find_one({"link": link}) is not None

def was_sent_recently(link, hours=24):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return sent_log_col.find_one({"link": link, "sent_at": {"$gte": cutoff}}) is not None

def log_sent(link):
    sent_log_col.insert_one({"link": link, "sent_at": datetime.utcnow()})

def save_airdrop_record(title, link, platform, score, twitter_url="N/A", xp="Unknown", description=""):
    doc = {
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
    }
    airdrops_col.insert_one(doc)

# ---------------------- Scam + Scoring Helpers ----------------------
def run_scam_checks(title, description, link):
    try:
        analyzer_res = analyze_airdrop(title, description, link) or {}
    except Exception as e:
        logging.exception("scam_analyzer error")
        analyzer_res = {"score": None, "verdict": "error", "details": {"error": str(e)}}

    try:
        basic_res = basic_scam_check((description or "") + " " + title + " " + link) or {}
    except Exception as e:
        logging.exception("basic_scam_check error")
        basic_res = {"is_scam": False, "flags": [], "error": str(e)}

    scam_score = analyzer_res.get("score", None)
    verdict = analyzer_res.get("verdict", None) or ("scam" if basic_res.get("is_scam") else "clean")

    return {
        "scam_score": scam_score,
        "verdict": verdict,
        "analyzer_details": analyzer_res,
        "basic_flags": basic_res
    }

def compute_rank_score(scam_score, twitter_score, xp):
    s = 50.0 if scam_score is None else float(scam_score)
    t = 50.0 if twitter_score is None else float(twitter_score)
    try:
        x = float(xp)
    except Exception:
        x = 0.0
    rank = (100.0 - s) * 0.45 + t * 0.35 + math.log1p(x) * 2.0
    return round(rank, 2)

# ---------------------- Messaging Helpers ----------------------
def send_telegram_message(chat_id, text, parse_mode="Markdown"):
    if not BOT_TOKEN:
        logging.warning("BOT_TOKEN not set; skipping telegram send.")
        return False
    send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": False}
    try:
        r = requests.post(send_url, json=payload, timeout=12)
        r.raise_for_status()
        return True
    except Exception as e:
        logging.error(f"[Telegram] send error to {chat_id}: {e}")
        return False

def broadcast_to_all_users(text, skip_admin=False):
    users = list(users_col.find({}))
    sent = 0
    for u in users:
        chat_id = u.get("chat_id")
        if not chat_id:
            continue
        if skip_admin and (str(chat_id) == str(ADMIN_ID) or chat_id == ADMIN_ID):
            continue
        ok = send_telegram_message(chat_id, text)
        if ok:
            sent += 1
        else:
            logging.debug(f"Failed to send to user {chat_id}")
        time.sleep(0.15)
    logging.info(f"Broadcast sent to {sent} users.")
    return sent

# ---------------------- Fetchers ----------------------
def fetch_explore_communities(limit=30, offset=0, sort="TRENDING"):
    variables = {"filter": "", "sort": sort, "limit": limit, "offset": offset}
    data = post_graphql(EXPLORE_QUERY, variables)
    if not data:
        return []
    try:
        communities = data.get("data", {}).get("exploreCommunities", []) or []
        return [{
            "title": c.get("name"),
            "slug": c.get("slug"),
            "url": build_zealy_url(c.get("slug")),
            "logo": c.get("logo"),
            "twitter": c.get("twitter"),
            "created_at": c.get("createdAt")
        } for c in communities]
    except Exception as e:
        logging.exception("Error parsing exploreCommunities response")
        return []

def fetch_community_quests_xp(slug, limit=12):
    variables = {"slug": slug, "limit": limit}
    data = post_graphql(COMMUNITY_QUESTS_QUERY, variables)
    if not data:
        return None, None
    try:
        community = data.get("data", {}).get("community")
        if not community:
            return None, None
        quests = community.get("quests") or []
        xp_values = []
        sample_desc = None
        for q in quests:
            if q.get("xp"):
                try:
                    xp_values.append(float(str(q["xp"]).replace(",", "")))
                except:
                    pass
            if not sample_desc:
                sample_desc = (q.get("title") or q.get("description") or "")
        max_xp = int(max(xp_values)) if xp_values else None
        return max_xp, sample_desc
    except Exception as e:
        logging.exception("Error parsing community quests")
        return None, None

# ---------------------- Processing & Sending ----------------------
def compose_public_message(title, url, xp, twitter_url, scam_summary):
    scam_line = f"{scam_summary.get('verdict','unknown')} (score: {scam_summary.get('scam_score','N/A')})"
    return (
        f"🚀 *{title}*\n"
        f"🎯 *XP:* {xp}\n"
        f"🔗 {url}\n"
        f"🐦 {twitter_url or 'N/A'}\n\n"
        f"*Scam Check:* {scam_line}\n"
        f"_Shared by @{OWNER_USERNAME}_"
    )

def compose_admin_message(title, url, xp, twitter_url, scam_summary, rank):
    analyzer = scam_summary.get("analyzer_details", {})
    basic = scam_summary.get("basic_flags", {})
    details_json = json.dumps(analyzer, default=str)[:1200]
    return (
        f"🧾 *Admin Report — New Airdrop Found*\n"
        f"Rank Score: *{rank}*\n"
        f"Project: *{title}*\n"
        f"XP: *{xp}*\n"
        f"Link: {url}\n"
        f"Twitter: {twitter_url or 'N/A'}\n\n"
        f"*Scam Analyzer Verdict:* {analyzer.get('verdict','N/A')}\n"
        f"*Basic Scam Flags:* {basic.get('flags', [])}\n"
        f"*Analyzer details:* `{details_json}`\n"
    )

def process_and_send(community):
    title = community.get("title") or "Unknown Project"
    slug = community.get("slug")
    url = community.get("url") or build_zealy_url(slug)
    twitter = community.get("twitter")

    if is_duplicate(url) or was_sent_recently(url, hours=24):
        return None

    xp_value, sample_desc = fetch_community_quests_xp(slug)
    xp_display = xp_value if xp_value is not None else "Unknown"
    should_send_now = xp_value is not None and 100 < xp_value < 1000

    scam_summary = run_scam_checks(title, sample_desc or "", url)
    twitter_score = rate_twitter_buzz(twitter) if twitter else None
    rank_score = compute_rank_score(
        scam_summary.get("scam_score", 50),
        twitter_score,
        xp_value or 0
    )

    full_title = f"{title} Quests"
    save_airdrop_record(full_title, url, "Zealy", rank_score, twitter, xp_display, sample_desc or "")
    log_sent(url)

    if should_send_now:
        broadcast_to_all_users(
            compose_public_message(full_title, url, xp_display, twitter, scam_summary),
            skip_admin=False
        )

    if ADMIN_ID:
        send_telegram_message(
            ADMIN_ID,
            compose_admin_message(full_title, url, xp_display, twitter, scam_summary, rank_score)
        )

    return {
        "title": full_title,
        "url": url,
        "xp": xp_value,
        "rank": rank_score,
        "scam": scam_summary,
        "sent_public": should_send_now
    }

# ---------------------- One-pass Scrape ----------------------
def run_scrape_once(limit=25, sort="TRENDING"):
    logging.info("Running Zealy scrape pass...")
    communities = fetch_explore_communities(limit=limit, sort=sort)
    if not communities:
        msg = f"⚠️ Zealy scrape returned no communities at {datetime.utcnow().isoformat()} UTC."
        logging.warning(msg)
        if ADMIN_ID:
            send_telegram_message(ADMIN_ID, msg)
        return []

    processed = []
    seen_slugs = set()
    for c in communities[:limit]:
        slug = c.get("slug")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        try:
            result = process_and_send(c)
            if result:
                processed.append(result)
        except Exception as e:
            logging.exception(f"Error processing community {slug}")
            if ADMIN_ID:
                send_telegram_message(ADMIN_ID, f"[❌] Error processing {slug}: {e}")
    
    logging.info(f"Scrape pass finished. Processed {len(processed)} items.")
    return processed

# ---------------------- Daily Trending ----------------------
def send_daily_trending(limit=12):
    logging.info("Preparing daily trending leaderboard...")
    communities = fetch_explore_communities(limit=limit, sort="TRENDING")
    if not communities:
        logging.warning("No trending communities found for daily report.")
        if ADMIN_ID:
            send_telegram_message(ADMIN_ID, "⚠️ Daily trending: no communities found.")
        return False

    scored = []
    for c in communities:
        slug = c.get("slug")
        xp_value, sample_desc = fetch_community_quests_xp(slug, limit=8)
        scam_summary = run_scam_checks(c.get("title"), sample_desc or "", c.get("url"))
        twitter_score = rate_twitter_buzz(c["twitter"]) if c.get("twitter") else None
        scored.append((
            compute_rank_score(
                scam_summary.get("scam_score", 50),
                twitter_score,
                xp_value or 0
            ),
            c,
            xp_value or 0,
            scam_summary
        ))

    scored.sort(reverse=True, key=lambda x: x[0])
    message = "\n".join(
        ["🔥 *Daily Top Trending Airdrops* 🔥"] +
        [f"{i}. *{c['title']}* — XP: {xp} — Rank: {rank}\nLink: {c['url']}\nVerdict: {s.get('verdict','N/A')}"
         for i, (rank, c, xp, s) in enumerate(scored[:limit], 1)]
    )

    if ADMIN_ID:
        send_telegram_message(ADMIN_ID, message)
        return True
    return False

# ---------------------- Runner / Scheduler ----------------------
def run_loop(poll_interval=POLL_INTERVAL, daily_hour=DAILY_HOUR_UTC):
    """Main loop: runs scrape every poll_interval seconds and sends daily trending at daily_hour UTC."""
    logging.info("Zealy scraper started. Poll interval: %s seconds. Daily hour (UTC): %s", poll_interval, daily_hour)
    last_daily_date = None  # track last date we ran daily to avoid repeats
    
    try:
        while True:
            try:
                run_scrape_once(limit=25, sort="TRENDING")
                
                # Daily trending check
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
            
    except KeyboardInterrupt:
        logging.info("Shutting down gracefully...")
    except Exception as e:
        logging.exception("Fatal error in main loop")

# This MUST be at the very bottom with NO indentation
if __name__ == "__main__":
    run_loop()
