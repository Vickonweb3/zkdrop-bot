#!/usr/bin/env python3
"""
Fetch all Zealy communities by paging the public communities endpoint.

Saves:
 - zealy_all_communities.json         (raw combined list)
 - zealy_all_communities_compact.json (compact slug/title/href list)

Run:
  python utils/scrapers/zealy_api_all.py
"""
from typing import Any, List
import requests
import time
import json
import sys

BASE = "https://api-v1.zealy.io/communities"
OUT_RAW = "zealy_all_communities.json"
OUT_COMPACT = "zealy_all_communities_compact.json"

SESSION = requests.Session()
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (compatible; ZealyAPIProbe/1.0)",
    "Referer": "https://zealy.io/explore",
}

LIMIT = 30         # keep same as observed; increase if API supports larger values
MAX_PAGES = 200    # safety cap to avoid infinite loops
SLEEP_BETWEEN = 0.5


def fetch_page(page: int, limit: int = LIMIT) -> Any:
    params = {"category": "all", "page": page, "limit": limit}
    r = SESSION.get(BASE, headers=HEADERS, params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def find_items(obj: Any) -> List:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("data", "communities", "items", "results"):
            if key in obj and isinstance(obj[key], list):
                return obj[key]
        # fallback: first list value
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


def main():
    all_items = []
    for page in range(0, MAX_PAGES):
        try:
            data = fetch_page(page)
        except requests.HTTPError as e:
            print(f"HTTP error fetching page {page}: {e}", file=sys.stderr)
            break
        except Exception as e:
            print(f"Error fetching page {page}: {e}", file=sys.stderr)
            break

        items = find_items(data)
        n = len(items)
        print(f"Fetched page {page}: {n} items")
        if n == 0:
            break
        all_items.extend(items)
        time.sleep(SLEEP_BETWEEN)

    # Save raw combined (best-effort)
    try:
        with open(OUT_RAW, "w", encoding="utf-8") as f:
            json.dump(all_items, f, indent=2, ensure_ascii=False)
        print(f"Saved raw combined -> {OUT_RAW}")
    except Exception as e:
        print("Failed to save raw JSON:", e, file=sys.stderr)

    normalized = [normalize_item(it if isinstance(it, dict) else {"raw": it}) for it in all_items]
    compact = [{"slug": n["slug"], "title": n["title"], "href": n["href"]} for n in normalized]

    try:
        with open(OUT_COMPACT, "w", encoding="utf-8") as f:
            json.dump(compact, f, indent=2, ensure_ascii=False)
        print(f"Saved compact -> {OUT_COMPACT}")
    except Exception as e:
        print("Failed to save compact JSON:", e, file=sys.stderr)

    print(f"Anchors found: {len(compact)} (listing up to 50)")
    for i, n in enumerate(compact[:50], start=1):
        print(f"{i}. slug='{n.get('slug')}' title='{n.get('title')}' href='{n.get('href')}'")


if __name__ == "__main__":
    main()
