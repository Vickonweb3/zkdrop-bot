#!/usr/bin/env python3
"""
Use Playwright to fetch the Zealy communities API from the browser context.

Run:
  python utils/scrapers/zealy_api_via_browser.py

Outputs:
  - zealy_browser_api.json
  - zealy_browser_api_compact.json
  - zealy_browser_api.png
  - zealy_browser_api.html
"""
import asyncio
import json
import sys
from typing import Any

from playwright.async_api import async_playwright

API_URL = "https://api-v1.zealy.io/communities?category=all&page=0&limit=30"
OUT_RAW = "zealy_browser_api.json"
OUT_COMPACT = "zealy_browser_api_compact.json"
SCREENSHOT = "zealy_browser_api.png"
HTML = "zealy_browser_api.html"


def find_items(obj: Any):
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


def normalize_item(it: dict):
    slug = it.get("slug") or it.get("handle") or it.get("id") or it.get("community_id")
    title = it.get("title") or it.get("name") or it.get("displayName") or it.get("label")
    href = it.get("href") or it.get("url")
    if not href and slug:
        href = f"/c/{slug}"
    return {"slug": slug, "title": title, "href": href, "raw": it}


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
            locale="en-US",
        )
        page = await context.new_page()

        try:
            await page.goto("https://zealy.io/explore", wait_until="networkidle", timeout=30000)
        except Exception as e:
            print("Warning: page.goto() failed:", e, file=sys.stderr)

        # Save page screenshot and HTML for debugging
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

        # Run fetch from page context so request uses browser headers/origin
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
            API_URL,
        )

        await browser.close()

    # Persist result
    try:
        with open(OUT_RAW, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Saved raw JSON -> {OUT_RAW}")
    except Exception as e:
        print("Warning: failed to save raw JSON:", e, file=sys.stderr)

    if "error" in result:
        print("ERROR fetching API from browser context:", result["error"], file=sys.stderr)
        sys.exit(1)

    status = result.get("status")
    json_body = result.get("json")
    print("API fetch status:", status)

    items = find_items(json_body) if json_body is not None else []
    normalized = [normalize_item(it if isinstance(it, dict) else {"raw": it}) for it in items]
    compact = [{"slug": n["slug"], "title": n["title"], "href": n["href"]} for n in normalized]

    # Save compact
    try:
        with open(OUT_COMPACT, "w", encoding="utf-8") as f:
            json.dump(compact, f, indent=2, ensure_ascii=False)
        print(f"Saved compact -> {OUT_COMPACT}")
    except Exception as e:
        print("Warning: failed to save compact JSON:", e, file=sys.stderr)

    print(f"Anchors found: {len(compact)} (listing up to 30)")
    for i, n in enumerate(compact[:30], start=1):
        print(f"{i}. slug='{n.get('slug')}' title='{n.get('title')}' href='{n.get('href')}'")


if __name__ == "__main__":
    asyncio.run(main())
