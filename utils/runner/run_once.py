#!/usr/bin/env python3
"""
Minimal runner to perform a single scrape run suitable for CI (GitHub Actions).
Calls run_scrape_once from utils.scrapers.zealy.

Usage:
  - python utils/runner/run_once.py         # single scrape run (uses SCRAPE_LIMIT env or default)
  - python utils/runner/run_once.py test    # run test_scraper() which sends a test message to ADMIN_ID
"""
import os
import sys
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("runner")

# import the scraper coroutine
try:
    # adjust module path if needed; this assumes utils/scrapers/zealy.py exists
    from utils.scrapers.zealy import run_scrape_once, test_scraper
except Exception as e:
    logger.exception("Failed to import utils.scrapers.zealy. Ensure file exists and is importable.")
    raise

def get_limit():
    v = os.getenv("SCRAPE_LIMIT", "25")
    try:
        return int(v)
    except Exception:
        return 25

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        logger.info("Running test_scraper() (will send message to ADMIN_ID if configured).")
        asyncio.run(test_scraper())
        sys.exit(0)

    limit = get_limit()
    logger.info("Starting single run_scrape_once(limit=%s)", limit)
    ok = asyncio.run(run_scrape_once(limit=limit))
    if ok:
        logger.info("run_scrape_once completed successfully.")
        sys.exit(0)
    else:
        logger.error("run_scrape_once reported failure.")
        sys.exit(1)
