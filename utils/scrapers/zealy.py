# main/utils/scrapers/zealy.py
"""
Zealy scraper for zkDrop Bot (long verbose version)
- GraphQL fetch for exploreCommunities
- Per-community quest fetch to estimate XP & description sample
- Filters immediate sends for 100 < XP < 1000
- Sends results immediately to ALL registered users and also to ADMIN
- Runs scam_analyzer + basic_scam_check and includes detailed admin report
- Stores airdrops in MongoDB and logs sends to avoid duplicates within 24h
- Sends a daily trending leaderboard at a fixed UTC hour
"""

import os
import json
import time
import math
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
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64)"
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
    # keep as string if not numeric
    pass

# ---------------------- Logging ----------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# ---------------------- MongoDB Setup ----------------------
mongo_client = MongoClient(MONGO_URI, tls=True, tlsAllowInvalidCertificates=True)
db = mongo_client.get_database("zkdrop_bot")
airdrops_col = db.get_collection("airdrops")      # stored airdrops (historical)
sent_log_col = db.get_collection("sent_log")      # recent sends for dedupe (24h)
users_col = db.get_collection("users")            # registered users where we send messages
# users collection expected docs: {"chat_id": <int or str>, "username": "...", ...}

# ---------------------- External Helpers (expected in repo) ----------------------
# Try to import real helpers from utils; if missing, use safe stubs so code still runs.
try:
    from utils.scam_analyzer import analyze_airdrop  # should return {"score":int,"verdict":str,"details":{}}
except Exception:
    logging.warning("utils.scam_analyzer not found. Using fallback analyzer stub.")
    def analyze_airdrop(title, description, url):
        return {"score": 50, "verdict": "unknown", "details": {"note": "fallback analyzer used"}}

# try two names for basic scam function
try:
    from utils.scam_filter import basic_scam_check
except Exception:
    try:
        from utils.scam_check import basic_scam_check
    except Exception:
        logging.warning("utils.scam_filter/basic_scam_check not found. Using fallback basic_scam_check.")
        def basic_scam_check(content):
            # fallback returns consistent shape
            return {"is_scam": False, "flags": []}

try:
    from utils.twitter_rating import rate_twitter_buzz
except Exception:
    logging.info("utils.twitter_rating not found. Using fallback rate_twitter_buzz.")
    def rate_twitter_buzz(handle_or_url):
        return 50  # neutral

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
    """Send a GraphQL POST and return parsed JSON or None on error."""
    payload = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    try:
        resp = requests.post(GRAPHQL_URL, headers=HEADERS, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logging.error(f"[GraphQL] request failed: {e}")
        return None

def build_zealy_url(slug):
    return f"https://zealy.io/c/{slug}"

def now_utc():
    return datetime.utcnow()

# ---------------------- DB Helpers ----------------------
def is_duplicate(link):
    """Return True if link already exists historically in airdrops collection."""
    return airdrops_col.find_one({"link": link}) is not None

def was_sent_recently(link, hours=24):
    """Return True if link was already sent within the last `hours` hours."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    return sent_log_col.find_one({"link": link, "sent_at": {"$gte": cutoff}}) is not None

def log_sent(link):
    """Log that a link was sent (for dedupe)."""
    sent_log_col.insert_one({"link": link, "sent_at": datetime.utcnow()})

def save_airdrop_record(title, link, platform, score, twitter_url="N/A", xp="Unknown", description=""):
    """Persist a standard airdrop doc in the `airdrops` collection."""
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
    """Run analyzer + basic scam check. Return unified dict."""
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

    combined = {
        "scam_score": scam_score,
        "verdict": verdict,
        "analyzer_details": analyzer_res,
        "basic_flags": basic_res
    }
    return combined

def compute_rank_score(scam_score, twitter_score, xp):
    """Return a single numeric rank (higher = better)."""
    s = 50.0 if scam_score is None else float(scam_score)
    t = 50.0 if twitter_score is None else float(twitter_score)
    try:
        x = float(xp)
    except Exception:
        x = 0.0
    # rank formula tuned: lower scam better, twitter higher better, xp increases rank with diminishing returns
    rank = (100.0 - s) * 0.45 + t * 0.35 + math.log1p(x) * 2.0
    return round(rank, 2)

# ---------------------- Messaging Helpers ----------------------
def send_telegram_message(chat_id, text, parse_mode="Markdown"):
    """Send message to a chat_id using BOT_TOKEN. Returns True on success."""
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
    """Send a text message to every user in users_col. If skip_admin True, skip ADMIN_ID."""
    users = list(users_col.find({}))
    sent = 0
    for u in users:
        chat_id = u.get("chat_id")
        if not chat_id:
            continue
        # Optionally skip admin if requested
        if skip_admin and (str(chat_id) == str(ADMIN_ID) or chat_id == ADMIN_ID):
            continue
        ok = send_telegram_message(chat_id, text)
        if ok:
            sent += 1
        else:
            logging.debug(f"Failed to send to user {chat_id}")
        time.sleep(0.15)  # small pause to avoid rate limits
    logging.info(f"Broadcast sent to {sent} users.")
    return sent

# ---------------------- Fetchers ----------------------
def fetch_explore_communities(limit=30, offset=0, sort="TRENDING"):
    """Fetch communities from Zealy explore GraphQL query."""
    variables = {"filter": "", "sort": sort, "limit": limit, "offset": offset}
    data = post_graphql(EXPLORE_QUERY, variables)
    if not data:
        return []
    try:
        communities = data.get("data", {}).get("exploreCommunities", []) or []
        results = []
        for c in communities:
            results.append({
                "title": c.get("name"),
                "slug": c.get("slug"),
                "url": build_zealy_url(c.get("slug")),
                "logo": c.get("logo"),
                "twitter": c.get("twitter"),
                "created_at": c.get("createdAt")
            })
        return results
    except Exception as e:
        logging.exception("Error parsing exploreCommunities response")
        return []

def fetch_community_quests_xp(slug, limit=12):
    """Best-effort fetch of quest XP values for a community; returns (max_xp:int or None, sample_desc:str or None)."""
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
            xp_raw = q.get("xp")
            # xp may be numeric or string like "100" or "100 XP"
            if xp_raw is not None:
                try:
                    xp_values.append(float(xp_raw))
                except Exception:
                    try:
                        digits = "".join(ch for ch in str(xp_raw) if (ch.isdigit() or ch in ".,"))
                        xp_values.append(float(digits.replace(",", "") or 0))
                    except Exception:
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
    msg = (
        f"🚀 *{title}*\n"
        f"🎯 *XP:* {xp}\n"
        f"🔗 {url}\n"
        f"🐦 {twitter_url or 'N/A'}\n\n"
        f"*Scam Check:* {scam_line}\n"
        f"_Shared by @{OWNER_USERNAME}_"
    )
    return msg

def compose_admin_message(title, url, xp, twitter_url, scam_summary, rank):
    analyzer = scam_summary.get("analyzer_details", {})
    basic = scam_summary.get("basic_flags", {})
    details_json = json.dumps(analyzer, default=str)
    # limit details length to avoid huge messages
    details_snippet = details_json if len(details_json) <= 1200 else details_json[:1190] + "..."
    msg = (
        f"🧾 *Admin Report — New Airdrop Found*\n"
        f"Rank Score: *{rank}*\n"
        f"Project: *{title}*\n"
        f"XP: *{xp}*\n"
        f"Link: {url}\n"
        f"Twitter: {twitter_url or 'N/A'}\n\n"
        f"*Scam Analyzer Verdict:* {analyzer.get('verdict','N/A')} (score: {analyzer.get('score','N/A')})\n"
        f"*Basic Scam Flags:* {basic.get('flags', basic.get('flag', []))}\n"
        f"*Analyzer details:* `{details_snippet}`\n"
        f"_Received at {datetime.utcnow().isoformat()} UTC_"
    )
    return msg

def process_and_send(community):
    """Main per-community processing pipeline: xp fetch -> filter -> scam checks -> save -> send to users + admin."""
    title = community.get("title") or "Unknown Project"
    slug = community.get("slug")
    url = community.get("url") or build_zealy_url(slug)
    twitter = community.get("twitter") or None

    # check historical duplicate
    if is_duplicate(url):
        logging.debug(f"Skipping historical duplicate: {url}")
        return None

    # check if already sent within 24h
    if was_sent_recently(url, hours=24):
        logging.debug(f"Skipping recently sent: {url}")
        return None

    # fetch xp & sample description
    xp_value, sample_desc = fetch_community_quests_xp(slug)
    xp_display = xp_value if xp_value is not None else "Unknown"

    # filter immediate send: XP > 100 and < 1000
    should_send_now = False
    if xp_value is not None:
        if xp_value > 100 and xp_value < 1000:
            should_send_now = True
    else:
        # if unknown xp, prefer not to spam users but still notify admin for review.
        should_send_now = False

    # run scam checks
    scam_summary = run_scam_checks(title, sample_desc or "", url)
    scam_score = scam_summary.get("scam_score", None)

    # twitter buzz rating
    twitter_score = None
    try:
        if twitter:
            twitter_score = rate_twitter_buzz(twitter)
    except Exception:
        logging.debug("twitter rating failed; continuing without twitter score")

    # compute admin rank
    rank_score = compute_rank_score(scam_score if scam_score is not None else 50, twitter_score, xp_value or 0)

    # Save record to DB (so it is tracked even if we don't send publicly)
    full_title = f"{title} Quests"
    save_airdrop_record(full_title, url, "Zealy", rank_score, twitter_url=twitter or "N/A", xp=xp_display, description=sample_desc or "")

    # log as sent (dedupe)
    log_sent(url)

    # compose messages
    public_msg = compose_public_message(full_title, url, xp_display, twitter, scam_summary)
    admin_msg = compose_admin_message(full_title, url, xp_display, twitter, scam_summary, rank_score)

    # send to all registered users if should_send_now
    if should_send_now:
        logging.info(f"Sending public message for {full_title} to all users.")
        broadcast_to_all_users(public_msg, skip_admin=False)  # skip_admin False -> admin also receives via users list if present

    # always send admin detailed report
    if ADMIN_ID:
        logging.info(f"Sending admin report for {full_title} to ADMIN_ID {ADMIN_ID}")
        send_telegram_message(ADMIN_ID, admin_msg)

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
    """Fetch communities and process them one by one. Returns list of processed results."""
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
        if not slug:
            continue
        if slug in seen_slugs:
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
    """Fetch trending communities and send a ranked leaderboard to admin."""
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
        xp_value = xp_value or 0
        scam_summary = run_scam_checks(c.get("title"), sample_desc or "", c.get("url"))
        twitter_score = None
        try:
            if c.get("twitter"):
                twitter_score = rate_twitter_buzz(c.get("twitter"))
        except Exception:
            twitter_score = None
        rank = compute_rank_score(scam_summary.get("scam_score", 50), twitter_score, xp_value)
        scored.append((rank, c, xp_value, scam_summary))

    # sort by rank descending
    scored.sort(reverse=True, key=lambda x: x[0])

    # build leaderboard message
    lines = ["🔥 *Daily Top Trending Airdrops* 🔥", f"_Report generated: {datetime.utcnow().isoformat()} UTC_\n"]
    for i, (rank, c, xp, scam_summary) in enumerate(scored[:limit], start=1):
        lines.append(f"{i}. *{c.get('title')}* — XP: {xp} — Rank: {rank}")
        lines.append(f"Link: {c.get('url')}")
        lines.append(f"Verdict: {scam_summary.get('verdict','N/A')} (score: {scam_summary.get('scam_score','N/A')})\n")

    message = "\n".join(lines)
    if ADMIN_ID:
        send_telegram_message(ADMIN_ID, message)
        logging.info("Daily trending leaderboard sent to admin.")
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
            except Exception as e:
                logging.exception("Main scrape error")
                if ADMIN_ID:
                    send_telegram_message(ADMIN_ID, f"[❌ Zealy main error] {e}")

            # daily trending check - run once each day at the configured UTC hour
            now = datetime.utcnow()
            today_date = now.date()
            if now.hour == daily_hour and (last_daily_date != today_date):
                try:
                    send_daily_trending(limit=12)
                    last_daily_date = today_date
except 
