#!/usr/bin/env python3
"""
Zealy scraper for zkDrop Bot (PLAYWRIGHT-ENHANCED)
- Primary discovery: requests-based paginated fetch with browser-like headers.
- Fallback discovery: Playwright browser-context paginated fetch (avoids 403).
- Secondary fallback: DOM scraping (anchors / grid / text) unchanged from original.
- Reuses Playwright browser/context for quest fetching (avoid launching per community).
- Preserves original DB saves and Telegram message format.

Place this file at: utils/scrapers/zealy.py
Run: python utils/scrapers/zealy.py  (runs main loop)
Test: python utils/scrapers/zealy.py test
"""
import os
import math
import random
import logging
import asyncio
import aiohttp
import json
import time
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pymongo import MongoClient

# ---------------------- Logging ----------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("zealy_scraper.log")
    ]
)
logger = logging.getLogger(__name__)

# ---------------------- Environment / Config ----------------------
try:
    from dotenv import load_dotenv
    load_dotenv()
    logger.info("Loaded .env file")
except Exception:
    logger.debug("python-dotenv not installed or .env missing; using system environment")

BASE_URL = "https://zealy.io"
API_BASE = "https://api-v1.zealy.io/communities"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

# Required configuration
MONGO_URI = os.getenv("MONGO_URI") or os.getenv("MONGO_URL") or os.getenv("DATABASE_URL")
if not MONGO_URI:
    raise RuntimeError("MONGO_URI environment variable is required")

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

# Optional configuration
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "VickOnWeb3")
POLL_INTERVAL = int(os.getenv("ZEALY_POLL_INTERVAL", "300"))  # seconds (default 5 min)
DAILY_HOUR_UTC = int(os.getenv("ZEALY_DAILY_HOUR_UTC", "9"))  # default 09:00 UTC
COMPACT_JSON_PATH = os.getenv("ZEALY_COMPACT_JSON", "zealy_browser_api_all_compact.json")
PAGE_LIMIT = int(os.getenv("ZEALY_PAGE_LIMIT", "30"))
MAX_PAGES = int(os.getenv("ZEALY_MAX_PAGES", "200"))

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
    mongo_client.admin.command('ping')
    logger.info("Successfully connected to MongoDB")

    db = mongo_client.get_database("zkdrop_bot")
    airdrops_col = db.get_collection("airdrops")
    sent_log_col = db.get_collection("sent_log")
    users_col = db.get_collection("users")

except Exception as e:
    logger.critical(f"MongoDB connection failed: {str(e)}")
    raise

# ---------------------- Utility helpers ----------------------
def now_utc():
    return datetime.utcnow()

def build_zealy_url(slug: str) -> str:
    return f"{BASE_URL}/c/{slug}"

def _compact_item_from_api(it: Dict[str, Any]) -> Dict[str, Any]:
    # API uses id and name; other shapes possible. Normalize to slug/title/href
    slug = it.get("id") or it.get("subdomain") or it.get("slug")
    title = it.get("name") or it.get("title") or it.get("label") or it.get("displayName")
    href = f"/c/{slug}" if slug else it.get("href") or it.get("url")
    return {
        "slug": slug,
        "title": title,
        "href": href,
        "raw": it
    }

def is_duplicate(link):
    try:
        return airdrops_col.find_one({"link": link}) is not None
    except Exception as e:
        logger.error(f"Duplicate check failed: {e}")
        return True  # fail-safe

def was_sent_recently(link, hours=24):
    try:
        cutoff = now_utc() - timedelta(hours=hours)
        return sent_log_col.find_one({"link": link, "sent_at": {"$gte": cutoff}}) is not None
    except Exception as e:
        logger.error(f"Sent recently check failed: {e}")
        return True  # fail-safe

def log_sent(link):
    try:
        sent_log_col.insert_one({
            "link": link,
            "sent_at": now_utc(),
            "processed": False
        })
    except Exception as e:
        logger.error(f"Failed to log sent message: {e}")

def save_airdrop_record(title, url, source, rank_score, twitter, xp_display, sample_desc):
    try:
        airdrops_col.insert_one({
            "title": title,
            "link": url,
            "source": source,
            "rank_score": rank_score,
            "twitter": twitter,
            "xp": xp_display,
            "description": sample_desc,
            "created_at": now_utc(),
            "processed": True
        })
    except Exception as e:
        logger.error(f"Failed to save airdrop: {e}")

# ---------------------- External optional helpers (fallbacks) ----------------------
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

# ---------------------- Scoring helpers ----------------------
def run_scam_checks(title, description, link):
    """
    Defensive wrapper around external analyzers that:
    - Catches exceptions from analyzers so failures don't crash the scraper.
    - Coerces non-dict returns into a small dict wrapper so .get() calls don't fail.
    This DOES NOT change analyzer logic or outputs; it only normalizes results.
    """
    analyzer_res = {}
    basic_res = {}

    # analyze_airdrop may raise or return non-dict — handle both
    try:
        raw = analyze_airdrop(title, description, link)
        if isinstance(raw, dict):
            analyzer_res = raw or {}
        else:
            # preserve the raw return value in analyzer_res['details']['raw']
            analyzer_res = {
                "score": raw if raw is not None and isinstance(raw, (int, float)) else None,
                "verdict": None,
                "details": {"raw": raw}
            }
    except Exception as e:
        logger.exception("scam_analyzer error")
        analyzer_res = {"score": None, "verdict": "error", "details": {"error": str(e)}}

    # basic_scam_check may raise or return non-dict — handle both
    try:
        rawb = basic_scam_check((description or "") + " " + title + " " + link)
        if isinstance(rawb, dict):
            basic_res = rawb or {}
        else:
            basic_res = {"is_scam": bool(rawb), "flags": [], "raw": rawb}
    except Exception as e:
        logger.exception("basic_scam_check error")
        basic_res = {"is_scam": False, "flags": [], "error": str(e)}

    scam_score = analyzer_res.get("score") if isinstance(analyzer_res, dict) else None
    verdict = analyzer_res.get("verdict") if isinstance(analyzer_res, dict) else None
    if not verdict:
        verdict = "scam" if basic_res.get("is_scam") else "clean"

    return {
        "scam_score": scam_score,
        "verdict": verdict,
        "analyzer_details": analyzer_res,
        "basic_flags": basic_res
    }

def compute_rank_score(scam_score, twitter_score, xp):
    """
    Defensive compute_rank_score:
    - tolerates non-numeric or None scam/twitter scores
    - uses safe defaults when conversion fails
    """
    # scam_score -> numeric fallback 50.0
    try:
        s = 50.0 if scam_score is None else float(scam_score)
    except Exception:
        logger.debug(f"compute_rank_score: invalid scam_score={scam_score!r}, using 50.0")
        s = 50.0

    # twitter_score -> numeric fallback 50.0
    try:
        t = 50.0 if twitter_score is None else float(twitter_score)
    except Exception:
        logger.debug(f"compute_rank_score: invalid twitter_score={twitter_score!r}, using 50.0")
        t = 50.0

    # xp -> numeric fallback 0.0
    try:
        x = float(xp)
    except Exception:
        x = 0.0

    rank = (100.0 - s) * 0.45 + t * 0.35 + math.log1p(x) * 2.0
    return round(rank, 2)

# ---------------------- Messaging helpers ----------------------
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

# ---------------------- Discovery: Requests-based paginated fetch ----------------------
import requests

def fetch_with_requests_paginated(limit: int = PAGE_LIMIT, max_pages: int = 10) -> List[Dict]:
    """
    Fast attempt to fetch communities pages using requests with browser-like headers.
    Raises requests.HTTPError if blocked (e.g., 403).
    """
    session = requests.Session()
    headers = {
        "Accept": "application/json, text/plain, */*",
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": f"{BASE_URL}/explore",
        "Origin": BASE_URL,
        "Sec-Fetch-Site": "same-site",
        "Sec-Fetch-Mode": "cors",
    }
    all_items: List[Dict] = []
    for page in range(0, max_pages):
        params = {"category": "all", "page": page, "limit": limit}
        resp = session.get(API_BASE, headers=headers, params=params, timeout=15)
        if resp.status_code == 403:
            # blocked
            raise requests.HTTPError(f"403 Forbidden for page {page}", response=resp)
        resp.raise_for_status()
        data = resp.json()
        # find list in known keys
        items = []
        if isinstance(data, dict):
            for k in ("communities", "data", "items", "results"):
                if k in data and isinstance(data[k], list):
                    items = data[k]
                    break
            if not items:
                # fallback: first list value
                for v in data.values():
                    if isinstance(v, list):
                        items = v
                        break
        elif isinstance(data, list):
            items = data
        if not items:
            break
        all_items.extend(items)
        # small delay to be polite
        time.sleep(0.15)
    return all_items

# ---------------------- Discovery: Browser-context paginated fetch (Playwright) ----------------------
async def fetch_with_playwright_paginated(limit: int = PAGE_LIMIT, max_pages: int = MAX_PAGES, save_compact: Optional[str]=None) -> List[Dict]:
    """
    Use Playwright to perform window.fetch() from page context to call the communities API
    and page through results. Returns list of raw items (un-normalized).
    """
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        raise RuntimeError("Playwright not available. Install playwright and run in Playwright-compatible environment.") from e

    all_items: List[Dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale="en-US",
        )
        page = await context.new_page()
        # Visit explore so site state is set (cookies, origins)
        try:
            await page.goto(f"{BASE_URL}/explore", wait_until="networkidle", timeout=30000)
        except Exception:
            logger.debug("Playwright: initial navigation warning; continuing")

        page_num = 0
        for _ in range(max_pages):
            url = f"{API_BASE}?category=all&page={page_num}&limit={limit}"
            result = await page.evaluate(
                """async (url) => {
                    try {
                        const res = await fetch(url, { method: 'GET', credentials: 'omit', headers: { 'Accept': 'application/json, text/plain, */*' } });
                        const status = res.status;
                        let json = null;
                        try { json = await res.json(); } catch(e) { json = null; }
                        return { status, json };
                    } catch (err) {
                        return { error: String(err) };
                    }
                }""",
                url,
            )
            if "error" in result:
                logger.error(f"Browser fetch error page {page_num}: {result['error']}")
                break
            status = result.get("status")
            if status != 200:
                logger.error(f"Non-200 status for page {page_num}: {status}")
                break
            json_body = result.get("json")
            # extract items
            items = []
            if isinstance(json_body, dict):
                for k in ("communities", "data", "items", "results"):
                    if k in json_body and isinstance(json_body[k], list):
                        items = json_body[k]
                        break
                if not items:
                    for v in json_body.values():
                        if isinstance(v, list):
                            items = v
                            break
            elif isinstance(json_body, list):
                items = json_body
            logger.info(f"Fetched page {page_num}: {len(items)} items (browser-context)")
            if not items:
                break
            all_items.extend(items)
            page_num += 1
            await asyncio.sleep(0.15)
        # Save compact if requested
        if save_compact:
            try:
                compact = [_compact_item_from_api(it) for it in all_items]
                with open(save_compact, "w", encoding="utf-8") as f:
                    json.dump(compact, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved compact JSON -> {save_compact}")
            except Exception as e:
                logger.warning(f"Failed to save compact JSON: {e}")
        await browser.close()
    return all_items

# ---------------------- High-level unified discovery ----------------------
def discover_communities(limit: int = 30, requests_pages_try: int = 10, save_compact: Optional[str] = COMPACT_JSON_PATH) -> List[Dict]:
    """
    Primary: try requests-first (fast). If requests blocked/returns nothing, try browser-context fetch.
    Returns compact normalized list: {slug,title,href,url,...}
    """
    raw_items: List[Dict] = []
    # Try requests first
    try:
        logger.info("Discovery: trying fast requests-based pagination...")
        raw_items = fetch_with_requests_paginated(limit=limit, max_pages=requests_pages_try)
        logger.info(f"Requests-based discovery returned {len(raw_items)} items")
    except Exception as e:
        logger.info(f"Requests-based discovery failed/blocked: {e}")

    # If requests returned nothing, fallback to browser
    if not raw_items:
        logger.info("Discovery: falling back to Playwright browser-context fetch...")
        try:
            raw_items = asyncio.run(fetch_with_playwright_paginated(limit=limit, max_pages=MAX_PAGES, save_compact=save_compact))
            logger.info(f"Browser-context discovery returned {len(raw_items)} items")
        except Exception as e:
            logger.warning(f"Browser-context discovery failed: {e}")
            # Last resort: try DOM scraping using a headless browser (reuse playwright if available)
            try:
                # attempt to run original anchor-based DOM scraper if Playwright available
                from playwright.async_api import async_playwright
                async def _dom_scrape():
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                        context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
                        page = await context.new_page()
                        await page.goto(f"{BASE_URL}/explore", wait_until="domcontentloaded", timeout=30000)
                        # reuse original anchor-based strategy minimal
                        await asyncio.sleep(2)
                        anchors = await page.query_selector_all("a[href*='/c/']")
                        items = []
                        seen = set()
                        for a in anchors:
                            try:
                                href = await a.get_attribute('href')
                                if not href or '/c/' not in href:
                                    continue
                                slug = href.split('/c/')[-1].split('/')[0]
                                if slug in seen:
                                    continue
                                seen.add(slug)
                                title = (await a.text_content()) or slug
                                items.append({"id": slug, "name": title.strip(), "subdomain": slug})
                                if len(items) >= limit:
                                    break
                            except Exception:
                                continue
                        await browser.close()
                        return items
                raw_items = asyncio.run(_dom_scrape())
                logger.info(f"DOM fallback discovery returned {len(raw_items)} items")
            except Exception as e2:
                logger.error(f"DOM fallback discovery also failed: {e2}")
                raw_items = []

    # Normalize to compact result
    compact = []
    seen_slugs = set()
    for it in raw_items:
        try:
            ci = _compact_item_from_api(it)
            slug = ci.get("slug") or ""
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            title = ci.get("title") or slug.replace('-', ' ').title()
            href = ci.get("href") or f"/c/{slug}"
            compact.append({
                "slug": slug,
                "title": title,
                "href": href,
                "url": f"{BASE_URL}{href}" if href.startswith("/") else href,
                "raw": ci.get("raw", it)
            })
            if len(compact) >= limit:
                break
        except Exception:
            continue

    # Save compact JSON to file for later use (non-fatal)
    if save_compact:
        try:
            with open(save_compact, "w", encoding="utf-8") as f:
                json.dump(compact, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved compact list -> {save_compact}")
        except Exception as e:
            logger.warning(f"Failed to save compact list: {e}")

    return compact

# ---------------------- Quest fetching (reusable browser/context) ----------------------
async def fetch_community_quests_with_page(page, slug: str, limit: int = 12) -> List[Dict]:
    """
    Uses the provided Playwright page (reused) to fetch quests for a community via DOM.
    This function assumes page is an open Playwright Page object.
    """
    try:
        url = f"{BASE_URL}/c/{slug}/questboard"
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # quick wait for React to hydrate
        await asyncio.sleep(3)
        quest_selectors = [
            '[data-testid*="quest"]',
            '[class*="quest"]',
            '[class*="Quest"]',
            'a[href*="/quest/"]',
            'div[class*="card"]',
            'li',
            'article'
        ]
        quests = []
        for selector in quest_selectors:
            try:
                elements = await page.query_selector_all(selector)
                if not elements:
                    continue
                for element in elements[:limit]:
                    try:
                        # title
                        title = None
                        title_elem = await element.query_selector('h3, h4, [class*="title"], [class*="Title"]')
                        if title_elem:
                            title = (await title_elem.text_content() or "").strip()
                        if not title:
                            title = (await element.text_content() or "").strip()[:100]
                        if not title:
                            continue
                        # xp
                        xp = None
                        xp_elem = await element.query_selector('[class*="xp"], [class*="XP"], [class*="reward"], [class*="Reward"]')
                        if xp_elem:
                            xp_text = await xp_elem.text_content()
                            if xp_text:
                                xp = ''.join(ch for ch in xp_text if ch.isdigit())
                        if not xp:
                            full_text = await element.text_content()
                            if full_text:
                                m = re.search(r'(\d+)\s*(?:XP|xp|point|pts)', full_text, re.IGNORECASE)
                                if m:
                                    xp = m.group(1)
                        if not xp:
                            xp = "100"
                        # description
                        description = None
                        desc_elem = await element.query_selector('p, [class*="description"], [class*="desc"]')
                        if desc_elem:
                            description = (await desc_elem.text_content() or "").strip()[:200]
                        if not description:
                            # get a snippet
                            text = await element.text_content()
                            if text:
                                sentences = text.strip().split('.')
                                for s in sentences:
                                    if len(s.strip()) > 20:
                                        description = s.strip()[:200]
                                        break
                        if not description:
                            description = title[:200]
                        quests.append({
                            "title": title,
                            "xp": xp,
                            "description": description
                        })
                        if len(quests) >= limit:
                            break
                    except Exception:
                        continue
                if quests:
                    break
            except Exception:
                continue
        # fallback: one default quest if none found
        if not quests:
            quests = [{
                'title': f"Join {slug} community",
                'xp': "500",
                'description': f"Complete quests in the {slug} community to earn rewards"
            }]
        return quests[:limit]
    except Exception as e:
        logger.error(f"Failed to fetch quests for {slug}: {e}")
        return [{
            'title': f"Join {slug} community",
            'xp': "500",
            'description': f"Complete quests in the {slug} community"
        }]

# ---------------------- Processing loop ----------------------
async def run_scrape_once(limit=25):
    """
    Single-run scraping pipeline:
     - Discover communities using discover_communities()
     - Reuse Playwright browser/page to fetch quests for communities
     - Score, save to DB and broadcast
    """
    logger.info("🚀 Running Zealy scrape cycle...")
    try:
        communities = discover_communities(limit=limit, requests_pages_try=3, save_compact=COMPACT_JSON_PATH)
        if not communities:
            logger.warning("No communities found in this scrape cycle")
            if ADMIN_ID:
                await send_telegram_message(ADMIN_ID, "⚠️ No communities found in scrape cycle")
            return False

        logger.info(f"Found {len(communities)} communities to process (using discovery)")

        # Prepare Playwright page once for quest fetching (if playwright available)
        playwright_available = True
        try:
            from playwright.async_api import async_playwright
        except Exception:
            playwright_available = False
            logger.info("Playwright not available locally; quest fetching will use defaults")

        page = None
        browser = None
        context = None
        if playwright_available:
            try:
                p = await async_playwright().start()
                browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
                page = await context.new_page()
            except Exception as e:
                logger.warning(f"Could not start Playwright for quests: {e}")
                page = None

        for c in communities:
            try:
                if is_duplicate(c['url']) or was_sent_recently(c['url']):
                    logger.debug(f"Skipping duplicate/recent: {c['title']}")
                    continue

                # Get quests for scam analysis
                sample_quests = []
                if page:
                    try:
                        sample_quests = await fetch_community_quests_with_page(page, c['slug'], limit=3)
                    except Exception as e:
                        logger.debug(f"Quest fetch error for {c['slug']}: {e}")
                        sample_quests = []
                else:
                    # fallback default quests
                    sample_quests = [{
                        'title': f"Join {c['title']}",
                        'xp': "500",
                        'description': f"Default quest for {c['title']}"
                    }]

                sample_desc = "\n".join([f"{q['title']} ({q.get('xp','?')} XP)" for q in sample_quests])

                # Run scam checks
                scam_summary = run_scam_checks(c['title'], sample_desc, c['url'])

                # Get Twitter buzz
                twitter_score = 50
                twitter_field = c.get('raw', {}).get('twitter') or c.get('raw', {}).get('twitter_handle') or c.get('raw', {}).get('twitterUrl') or c.get('raw', {}).get('twitter')
                if twitter_field:
                    try:
                        twitter_score = rate_twitter_buzz(twitter_field)
                    except Exception:
                        twitter_score = 50

                # Calculate XP (use max XP from quests)
                xp_values = []
                for q in sample_quests:
                    xp_raw = q.get('xp')
                    try:
                        if xp_raw:
                            xp_values.append(int(str(xp_raw).replace(',', '')))
                    except Exception:
                        continue
                xp_display = max(xp_values) if xp_values else "?"

                # Calculate rank score
                rank_score = compute_rank_score(
                    scam_summary.get('scam_score'),
                    twitter_score,
                    xp_display if isinstance(xp_display, (int, float)) else 0
                )

                # Save record
                save_airdrop_record(
                    c['title'],
                    c['url'],
                    "zealy",
                    rank_score,
                    twitter_field,
                    xp_display,
                    sample_desc
                )

                # Prepare and send message (same template you used)
                verdict = scam_summary.get('verdict', 'unknown')
                if verdict == 'scam':
                    logger.info(f"🚨 Scam detected: {c['title']}")
                    # Optionally still save but skip broadcast
                    continue

                message = (
                    f"🔥 *New Zealy Airdrop Found!*\\n\\n"
                    f"*{c['title']}*\\n"
                    f"XP: {xp_display}\\n"
                    f"Rank: {rank_score}\\n"
                    f"Verdict: {verdict}\\n\\n"
                    f"Link: {c['url']}"
                )

                await broadcast_to_all_users(message, skip_admin=True)
                log_sent(c['url'])

                logger.info(f"✅ Processed: {c['title']}")
                # polite rate limiting between community processing
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error processing community {c.get('title')}: {e}")
                continue

        # cleanup playwright
        if page:
            try:
                await page.close()
            except Exception:
                pass
        if context:
            try:
                await context.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass

        return True

    except Exception as e:
        logger.error(f"Scrape cycle failed: {e}")
        if ADMIN_ID:
            await send_telegram_message(ADMIN_ID, f"[❌ Zealy run_scrape_once error] {str(e)[:200]}")
        return False

# ---------------------- Daily trending ----------------------
# Replace the existing send_daily_trending function with this version.
async def send_daily_trending(limit=12, send_to_admin=True):
    """
    Build and optionally send the daily trending digest.
    Returns the digest message (string) or None if nothing to send.
    """
    try:
        cutoff = now_utc() - timedelta(hours=48)
        records = list(airdrops_col.find({
            "created_at": {"$gte": cutoff},
            "processed": True
        }).sort("rank_score", -1).limit(50))

        if not records:
            logger.info("No recent airdrops for daily trending")
            return None

        scored = []
        for r in records:
            try:
                scam_summary = run_scam_checks(r['title'], r.get('description', ''), r['link'])
                twitter_score = rate_twitter_buzz(r.get('twitter', ''))
                xp_value = int(r['xp']) if str(r['xp']).isdigit() else 0

                scored.append((
                    compute_rank_score(
                        scam_summary.get("scam_score", 50),
                        twitter_score,
                        xp_value or 0
                    ),
                    r,
                    xp_value or 0,
                    scam_summary
                ))
            except Exception as e:
                logger.error(f"Error scoring record {r.get('title')}: {e}")
                continue

        scored.sort(reverse=True, key=lambda x: x[0])

        # Build an attractive digest for users
        digest_lines = ["🔥 *Daily Top Trending Airdrops* 🔥", ""]
        for i, (rank, c, xp, s) in enumerate(scored[:limit], 1):
            title = c.get('title', 'Unknown')[:80]
            link = c.get('link', '')
            verdict = s.get('verdict', 'N/A') if s else 'N/A'
            digest_lines.append(f"{i}. *{title}* — XP: *{xp}* — Rank: *{rank}*\nLink: {link}\nVerdict: {verdict}\n")

        digest_lines.append("🔎 Tip: Check the most promising drops early. Stay safe and never share private keys.")
        message = "\n".join(digest_lines)

        # Optionally send to admin as well
        if send_to_admin and ADMIN_ID:
            try:
                await send_telegram_message(ADMIN_ID, message)
            except Exception:
                logger.exception("Failed to send daily trending to ADMIN_ID")

        # Return digest so scheduler can broadcast it to all users
        return message

    except Exception as e:
        logger.error(f"Daily trending failed: {e}")
        return None

# ---------------------- Runner / Scheduler ----------------------
async def run_loop(poll_interval=POLL_INTERVAL, daily_hour=DAILY_HOUR_UTC):
    logger.info("🚀 Zealy scraper started. Poll interval: %s seconds. Daily hour (UTC): %s", poll_interval, daily_hour)
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
        logger.exception("Critical error in main loop")
        if ADMIN_ID:
            await send_telegram_message(ADMIN_ID, f"[🚨 Critical Error] {str(e)[:200]}")

# ---------------------- Test Function ----------------------
async def test_scraper():
    logger.info("🧪 Testing Zealy scraper (discover + single quest fetch)...")
    try:
        communities = discover_communities(limit=5, requests_pages_try=3, save_compact=None)
        if not communities:
            logger.error("❌ No communities found!")
            if ADMIN_ID:
                await send_telegram_message(ADMIN_ID, "🧪 Test failed: No communities found")
            return False
        logger.info(f"✅ Found {len(communities)} communities:")
        test_results = []
        # attempt one Playwright quest fetch
        page = None
        try:
            from playwright.async_api import async_playwright
            p = await async_playwright().start()
            browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
            page = await context.new_page()
        except Exception:
            page = None

        for i, c in enumerate(communities, 1):
            logger.info(f"  {i}. {c['title']} ({c['slug']})")
            test_results.append(f"{i}. {c['title']} ({c['slug']})")
            if i == 1:
                try:
                    if page:
                        quests = await fetch_community_quests_with_page(page, c['slug'], limit=3)
                    else:
                        quests = [{
                            'title': f"Join {c['title']}",
                            'xp': "500",
                            'description': f"Default quest for {c['title']}"
                        }]
                    if quests:
                        logger.info(f"     Quests: {len(quests)} found")
                        test_results.append(f"     Quests: {len(quests)} found")
                        for j, quest in enumerate(quests[:2], 1):
                            logger.info(f"       {j}. {quest.get('title','Unknown')[:50]}... XP: {quest.get('xp','Unknown')}")
                    else:
                        logger.info("     Quests: None found")
                        test_results.append("     Quests: None found")
                except Exception as e:
                    logger.error(f"     Quest fetch failed: {e}")
                    test_results.append(f"     Quest fetch failed: {str(e)[:100]}")

        if page:
            try:
                await page.close()
                await context.close()
                await browser.close()
            except Exception:
                pass

        if ADMIN_ID and test_results:
            test_message = "🧪 *Zealy Scraper Test Results*\n\n" + "\n".join(test_results[:20])
            await send_telegram_message(ADMIN_ID, test_message)
        return True
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        if ADMIN_ID:
            await send_telegram_message(ADMIN_ID, f"🧪 Test failed: {str(e)[:200]}")
        return False

# ---------------------- Main ----------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_scraper())
    else:
        asyncio.run(run_loop())
