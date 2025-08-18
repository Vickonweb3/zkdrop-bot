#!/usr/bin/env python3
"""
Fetch all Zealy communities by calling the communities API from the browser context
(using Playwright). This avoids the 403 that occurs when calling the API directly
from requests.

Outputs:
 - zealy_browser_api_all_raw.json
 - zealy_browser_api_all_compact.json
 - zealy_browser_api_all.png
 - zealy_browser_api_all.html

Run:
  python utils/scrapers/zealy_api_via_browser_all.py
"""
import asyncio
import json
import sys
import time
from typing import Any, Dict, List

from playwright.async_api import async_playwright

BASE = "https://api-v1.zealy.io/communities"
OUT_RAW = "zealy_browser_api_all_raw.json"
OUT_COMPACT = "zealy_browser_api_all_compact.json"
SCREENSHOT = "zealy_browser_api_all.png"
HTML = "zealy_browser_api_all.html"
PAGE_LIMIT = 30
MAX_PAGES = 200
SLEEP_BETWEEN = 0.25  # safe pacing


def find_items(obj: Any) -> List:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("data", "communities", "items", "results"):
            if key in obj and isinstance(obj[key], list):
                return obj[key]
        for v in obj.values():
            if isinstance(v, list):
                return v
    return []


def normalize_item(it: dict) -> Dict:
    slug = it.get("slug") or it.get("handle") or it.get("id") or it.get("community_id")
    title = it.get("title") or it.get("name") or it.get("displayName") or it.get("label")
    href = it.get("href") or it.get("url")
    if not href and slug:
        href = f"/c/{slug}"
    return {"slug": slug, "title": title, "href": href, "raw": it}


async def fetch_page_from_browser(page, page_num: int, limit: int = PAGE_LIMIT):
    url = f"{BASE}?category=all&page={page_num}&limit={limit}"
    # run fetch from page context so request uses browser headers/origin
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
    return result


async def main():
    all_items = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            locale="en-US",
        )
        page = await context.new_page()

        # visit explore page first to ensure any site-side state is set
        try:
            await page.goto("https://zealy.io/explore", wait_until="networkidle", timeout=30000)
        except Exception:
            # continue even if the navigation warning occurs
            pass

        # screenshot and html for debugging
        try:
            await page.screenshot(path=SCREENSHOT, full_page=True)
        except Exception:
            pass
        try:
            content = await page.content()
            with open(HTML, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception:
            pass

        page_num = 0
        for i in range(MAX_PAGES):
            print(f"Browser-fetch page {page_num} ...")
            result = await fetch_page_from_browser(page, page_num)
            if "error" in result:
                print("ERROR (browser fetch):", result["error"], file=sys.stderr)
                break
            status = result.get("status")
            json_body = result.get("json")
            if status != 200:
                print(f"Non-200 status for page {page_num}: {status}", file=sys.stderr)
                break
            items = find_items(json_body) if json_body is not None else []
            print(f"Fetched page {page_num}: {len(items)} items")
            if not items:
                break
            all_items.extend(items)
            page_num += 1
            # optional small delay between page fetches
            time.sleep(SLEEP_BETWEEN)

        await browser.close()

    # Save raw combined
    try:
        with open(OUT_RAW, "w", encoding="utf-8") as f:
            json.dump({"fetchedPages": page_num, "items": all_items}, f, indent=2, ensure_ascii=False)
        print(f"Saved raw combined -> {OUT_RAW}")
    except Exception as e:
        print("Warning: failed to save raw JSON:", e, file=sys.stderr)

    normalized = [normalize_item(it if isinstance(it, dict) else {"raw": it}) for it in all_items]
    compact = [{"slug": n["slug"], "title": n["title"], "href": n["href"]} for n in normalized]

    try:
        with open(OUT_COMPACT, "w", encoding="utf-8") as f:
            json.dump(compact, f, indent=2, ensure_ascii=False)
        print(f"Saved compact -> {OUT_COMPACT}")
    except Exception as e:
        print("Warning: failed to save compact JSON:", e, file=sys.stderr)

    print(f"Anchors found: {len(compact)} (listing up to 200)")
    for i, n in enumerate(compact[:200], start=1):
        print(f"{i}. slug='{n.get('slug')}' title='{n.get('title')}' href='{n.get('href')}'")


if __name__ == "__main__":
    asyncio.run(main())
