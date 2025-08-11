#!/bin/bash
pip install -r requirements.txt

# Skip system dependencies - use pre-downloaded binaries
PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1 pip install playwright
wget https://playwright.azureedge.net/builds/chromium/1105/chromium-linux.zip -O /tmp/chromium.zip
unzip /tmp/chromium.zip -d /tmp/ms-playwright/chromium-1105
