"""
Zealy scraper for zkDrop Bot (PLAYWRIGHT EDITION)
All original functionality + critical upgrades:
1. Secure MongoDB TLS
2. Zealy rate limiting
3. Random user-agents
4. Playwright headless browser
5. Advanced anti-detection
6. Proper async/await handling
"""

import os
import json
import math
import random
import logging
import asyncio
import aiohttp
from datetime import datetime, timedelta
from pymongo import MongoClient
from urllib.parse import urljoin
from playwright.async_api import async_playwright

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("zealy_scraper.log")
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded .env file")
except ImportError:
    logger.warning("python-dotenv not installed, using system environment")

# ---------------------- Configuration ----------------------
BASE_URL = "https://zealy.io"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Mozilla/5.0 (X11; Linux x86_64)"
]

# Required configuration
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGO_URL") or os.getenv("DATABASE_URL")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is required")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Optional configuration
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "VickOnWeb3")
POLL_INTERVAL = int(os.getenv("ZEALY_POLL_INTERVAL", "300"))  # 5 minutes default
DAILY_HOUR_UTC = int(os.getenv("ZEALY_DAILY_HOUR_UTC", "9"))  # 9 AM UTC default

# ---------------------- MongoDB Setup ----------------------
try:
    mongo_client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsAllowInvalidCertificates=False,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=10000,
        socketTimeoutMS=30000,
        retryWrites=True,
        retryReads=True
    )
    mongo_client.admin.command('ping')  # Test connection
    logger.info("Successfully connected to MongoDB")
    
    db = mongo_client.get_database("zkdrop_bot")
    airdrops_col = db.get_collection("airdrops")
    sent_log_col = db.get_collection("sent_log")
    users_col = db.get_collection("users")
    
except Exception as e:
    logger.critical(f"MongoDB connection failed: {str(e)}")
    raise

# ---------------------- Helper Functions ----------------------
def build_zealy_url(slug):
    return f"{BASE_URL}/c/{slug}"

def now_utc():
    return datetime.utcnow()

def is_duplicate(link):
    try:
        return airdrops_col.find_one({"link": link}) is not None
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")
        return True  # Fail safe

def was_sent_recently(link, hours=24):
    try:
        cutoff = now_utc() - timedelta(hours=hours)
        return sent_log_col.find_one({"link": link, "sent_at": {"$gte": cutoff}}) is not None
    except Exception as e:
        logger.error(f"Sent recently check failed: {e}")
        return True  # Fail safe

def log_sent(link):
    try:
        sent_log_col.insert_one({
            "link": link,
            "sent_at": now_utc(),
            "processed": False
        })
    except Exception as e:
        logger.error(f"Failed to log sent message: {e}")

# ---------------------- External Helpers ----------------------
try:
    from utils.scam_analyzer import analyze_airdrop
except Exception:
    logger.warning("utils.scam_analyzer not found. Using fallback analyzer stub.")
    def analyze_airdrop(title, description, url):
        return {"score": 50, "verdict": "unknown", "details": {"note": "fallback analyzer used"}}

try:
    from utils.scam_filter import basic_scam_check
except Exception:
    try:
        from utils.scam_check import basic_scam_check
    except Exception:
        logger.warning("utils.scam_filter/basic_scam_check not found. Using fallback basic_scam_check.")
        def basic_scam_check(content):
            return {"is_scam": False, "flags": []}

try:
    from utils.twitter_rating import rate_twitter_buzz
except Exception:
    logger.info("utils.twitter_rating not found. Using fallback rate_twitter_buzz.")
    def rate_twitter_buzz(handle_or_url):
        return 50

# ---------------------- Scam + Scoring Helpers ----------------------
def run_scam_checks(title, description, link):
    try:
        analyzer_res = analyze_airdrop(title, description, link) or {}
    except Exception as e:
        logger.exception("scam_analyzer error")
        analyzer_res = {"score": None, "verdict": "error", "details": {"error": str(e)}}

    try:
        basic_res = basic_scam_check((description or "") + " " + title + " " + link) or {}
    except Exception as e:
        logger.exception("basic_scam_check error")
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
async def send_telegram_message(chat_id, text, parse_mode="Markdown"):
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN not set; skipping telegram send.")
        return False
    
    send_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": False
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(send_url, json=payload, timeout=12) as resp:
                resp.raise_for_status()
                return True
    except Exception as e:
        logger.error(f"[Telegram] send error to {chat_id}: {e}")
        return False

async def broadcast_to_all_users(text, skip_admin=False):
    try:
        users = list(users_col.find({}))
        sent = 0
        for u in users:
            chat_id = u.get("chat_id")
            if not chat_id:
                continue
            if skip_admin and (str(chat_id) == str(ADMIN_ID) or chat_id == ADMIN_ID):
                continue
            ok = await send_telegram_message(chat_id, text)
            if ok:
                sent += 1
            else:
                logger.debug(f"Failed to send to user {chat_id}")
            await asyncio.sleep(0.15)
        logger.info(f"Broadcast sent to {sent} users.")
        return sent
    except Exception as e:
        logger.error(f"Broadcast failed: {e}")
        return 0

# ---------------------- Playwright Scrapers ----------------------
async def fetch_explore_communities(limit=30):
    results = []
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1280, "height": 1024}
            )
            
            page = await context.new_page()
            await page.goto(f"{BASE_URL}/explore", wait_until="networkidle", timeout=30000)
            
            await page.wait_for_selector(".community-card", timeout=15000)
            
            # Scroll to load more
            for _ in range(2):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1)
            
            cards = await page.query_selector_all(".community-card")
            for card in cards[:limit]:
                try:
                    title = await card.get_attribute("data-name")
                    slug = await card.get_attribute("data-slug")
                    logo = await card.query_selector("img")
                    logo_url = await logo.get_attribute("src") if logo else None
                    twitter_elem = await card.query_selector(".twitter-link")
                    twitter = await twitter_elem.get_attribute("href") if twitter_elem else None
                    
                    results.append({
                        "title": title,
                        "slug": slug,
                        "url": build_zealy_url(slug),
                        "logo": logo_url,
                        "twitter": twitter
                    })
                except Exception as e:
                    logger.warning(f"Error parsing card: {e}")
                    continue
            
            return results[:limit]
        except Exception as e:
            logger.error(f"Explore communities scrape failed: {e}")
            return []
        finally:
            await browser.close()

async def fetch_community_quests(slug, limit=12):
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage"
                ]
            )
            context = await browser.new_context(
                user_agent=random.choice(USER_AGENTS)
            )
            
            page = await context.new_page()
            url = f"{BASE_URL}/c/{slug}/questboard"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            
            try:
                await page.wait_for_selector(".quest-item", timeout=15000)
            except:
                logger.warning(f"No quests found for {slug}")
                return None
            
            quests = []
            items = await page.query_selector_all(".quest-item")
            for item in items[:limit]:
                try:
                    title_elem = await item.query_selector(".quest-title")
                    title = await title_elem.text_content() if title_elem else None
                    
                    xp_elem = await item.query_selector(".quest-xp")
                    xp = await xp_elem.text_content() if xp_elem else None
                    
                    desc_elem = await item.query_selector(".quest-description")
                    description = await desc_elem.text_content() if desc_elem else None
                    
                    quests.append({
                        "title": title.strip() if title else None,
                        "xp": xp.strip() if xp else None,
                        "description": description.strip() if description else None
                    })
                except Exception as e:
                    logger.warning(f"Error parsing quest item: {e}")
                    continue
            
            return quests
        except Exception as e:
            logger.error(f"Community quests scrape failed for {slug}: {e}")
            return None
        finally:
            await browser.close()

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

async def process_and_send(community):
    try:
        title = community.get("title") or "Unknown Project"
        slug = community.get("slug")
        url = community.get("url") or build_zealy_url(slug)
        twitter = community.get("twitter")

        if is_duplicate(url) or was_sent_recently(url, hours=24):
            return None

        quests = await fetch_community_quests(slug)
        if not quests:
            return None

        xp_values = []
        sample_desc = None
        for q in quests:
            try:
                if q.get("xp"):
                    xp = int(''.join(filter(str.isdigit, q["xp"])))
                    xp_values.append(xp)
            except:
                pass
            if not sample_desc and q.get("description"):
                sample_desc = q["description"]

        max_xp = max(xp_values) if xp_values else None
        xp_display = max_xp if max_xp is not None else "Unknown"
        should_send_now = max_xp is not None and 100 < max_xp < 1000

        scam_summary = run_scam_checks(title, sample_desc or "", url)
        twitter_score = rate_twitter_buzz(twitter) if twitter else None
        rank_score = compute_rank_score(
            scam_summary.get("scam_score", 50),
            twitter_score,
            max_xp or 0
        )

        full_title = f"{title} Quests"
        save_airdrop_record(full_title, url, "Zealy", rank_score, twitter, xp_display, sample_desc or "")
        log_sent(url)

        if should_send_now:
            await broadcast_to_all_users(
                compose_public_message(full_title, url, xp_display, twitter, scam_summary),
                skip_admin=False
            )

        if ADMIN_ID:
            await send_telegram_message(
                ADMIN_ID,
                compose_admin_message(full_title, url, xp_display, twitter, scam_summary, rank_score)
            )

        return {
            "title": full_title,
            "url": url,
            "xp": max_xp,
            "rank": rank_score,
            "scam": scam_summary,
            "sent_public": should_send_now
        }
    except Exception as e:
        logger.error(f"Error processing community {community.get('slug')}: {e}")
        return None

# ---------------------- Main Scraping Functions ----------------------
async def run_scrape_once(limit=25):
    logger.info("Running Zealy scrape pass...")
    try:
        communities = await fetch_explore_communities(limit=limit)
    except Exception as e:
        msg = f"⚠️ Zealy scrape failed: {str(e)[:200]}"
        logger.error(msg)
        if ADMIN_ID:
            await send_telegram_message(ADMIN_ID, msg)
        return []

    if not communities:
        msg = f"⚠️ Zealy scrape returned no communities at {datetime.utcnow().isoformat()} UTC."
        logger.warning(msg)
        if ADMIN_ID:
            await send_telegram_message(ADMIN_ID, msg)
        return []

    processed = []
    seen_slugs = set()
    for c in communities[:limit]:
        slug = c.get("slug")
        if not slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        try:
            result = await process_and_send(c)
            if result:
                processed.append(result)
        except Exception as e:
            logger.exception(f"Error processing community {slug}")
            if ADMIN_ID:
                await send_telegram_message(ADMIN_ID, f"[❌] Error processing {slug}: {e}")
    
    logger.info(f"Scrape pass finished. Processed {len(processed)} items.")
    return processed

async def send_daily_trending(limit=12):
    logger.info("Preparing daily trending leaderboard...")
    try:
        communities = await fetch_explore_communities(limit=limit)
    except Exception as e:
        logger.error(f"Failed to fetch communities for daily report: {e}")
        if ADMIN_ID:
            await send_telegram_message(ADMIN_ID, "⚠️ Daily trending: fetch failed.")
        return False

    if not communities:
        logger.warning("No trending communities found for daily report.")
        if ADMIN_ID:
            await send_telegram_message(ADMIN_ID, "⚠️ Daily trending: no communities found.")
        return False

    scored = []
    for c in communities:
        slug = c.get("slug")
        quests = await fetch_community_quests(slug, limit=8)
        if not quests:
            continue
            
        xp_values = []
        sample_desc = None
        for q in quests:
            try:
                if q.get("xp"):
                    xp = int(''.join(filter(str.isdigit, q["xp"])))
                    xp_values.append(xp)
            except:
                pass
            if not sample_desc and q.get("description"):
                sample_desc = q["description"]

        xp_value = max(xp_values) if xp_values else 0
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
        await send_telegram_message(ADMIN_ID, message)
        return True
    return False

# ---------------------- Runner / Scheduler ----------------------
async def run_loop(poll_interval=POLL_INTERVAL, daily_hour=DAILY_HOUR_UTC):
    """Main loop: runs scrape every poll_interval seconds and sends daily trending at daily_hour UTC."""
    logger.info("Zealy scraper started. Poll interval: %s seconds. Daily hour (UTC): %s", poll_interval, daily_hour)
    last_daily_date = None
    
    try:
        while True:
            try:
                await run_scrape_once(limit=25)
                
                now = datetime.utcnow()
                today_date = now.date()
                if now.hour == daily_hour and (last_daily_date != today_date):
                    try:
                        await send_daily_trending(limit=12)
                        last_daily_date = today_date
                    except Exception as e:
                        logger.error(f"Daily trending failed: {e}")
                        
            except Exception as e:
                logger.exception("Main scrape error")
                if ADMIN_ID:
                    await send_telegram_message(ADMIN_ID, f"[❌ Zealy main error] {str(e)[:200]}")
            
            await asyncio.sleep(poll_interval)
            
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.exception("Fatal error in main loop")

# ---------------------- Main Execution ----------------------
if __name__ == "__main__":
    try:
        asyncio.run(run_loop())
    except Exception as e:
        logger.critical(f"Application crashed: {e}")
        raise
