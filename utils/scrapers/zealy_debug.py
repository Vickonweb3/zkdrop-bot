import asyncio
import random
import logging
from pathlib import Path
from playwright.async_api import async_playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("zealy-debug")

OUT_DIR = Path.cwd()

async def main():
    url = "https://zealy.io/explore"
    network_logs = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1400, "height": 900}
        )

        try:
            await context.add_init_script(
                "() => { Object.defineProperty(navigator, 'webdriver', {get: () => false}); "
                "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']}); "
                "window.navigator.chrome = { runtime: {} }; }"
            )
        except Exception:
            pass

        page = await context.new_page()
        page.on("console", lambda msg: logger.info(f"PAGE LOG [{msg.type}] {msg.text}"))

        def on_response(resp):
            try:
                u = resp.url
                s = resp.status
                if "/api" in u or "graphql" in u or "/quest" in u or "/explore" in u:
                    network_logs.append(f"{s} {u}")
            except Exception:
                pass

        page.on("response", on_response)

        logger.info(f"Loading: {url}")
        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception as e:
            logger.warning(f"page.goto warning/timeout: {e}")

        try:
            await page.wait_for_selector("a[href*='/c/']", timeout=15000)
            logger.info("Found at least one community anchor (a[href*='/c/']).")
        except Exception:
            logger.info("No community anchors found within wait timeout.")

        try:
            for _ in range(3):
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(1.0)
        except Exception:
            pass

        try:
            png_path = OUT_DIR / "zealy_debug.png"
            await page.screenshot(path=str(png_path), full_page=True)
            logger.info(f"Saved screenshot: {png_path}")
        except Exception as e:
            logger.warning(f"Could not save screenshot: {e}")

        try:
            html = await page.content()
            html_path = OUT_DIR / "zealy_debug.html"
            html_path.write_text(html, encoding="utf-8")
            logger.info(f"Saved HTML: {html_path} ({len(html)} bytes)")
        except Exception as e:
            logger.warning(f"Could not save HTML: {e}")

        anchors = await page.query_selector_all("a[href*='/c/']")
        found = []
        for a in anchors[:200]:
            try:
                href = await a.get_attribute("href")
                if not href:
                    continue
                slug = href.split("/c/")[-1].split("/")[0].split("?")[0].split("#")[0]
                if slug and len(slug) > 1:
                    title = (await a.text_content()) or ""
                    found.append({"href": href, "slug": slug, "title": title.strip()[:80]})
            except Exception:
                continue

        try:
            net_path = OUT_DIR / "zealy_network.log"
            net_path.write_text("\n".join(network_logs), encoding="utf-8")
            logger.info(f"Saved network log: {net_path}")
        except Exception:
            pass

        logger.info(f"Anchors found: {len(found)} (listing up to 20)")
        for i, item in enumerate(found[:20], start=1):
            logger.info(f"{i}. slug='{item['slug']}' title='{item['title']}' href='{item['href']}'")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
