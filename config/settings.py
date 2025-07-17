import os

# 🔐 Secure credentials
BOT_TOKEN = os.getenv("BOT_TOKEN", "7245698081:AAHvSwVjJ5xsjOXOKRVTtopOterqCGAAMFw")
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://zkadmin:nnamdi2010@zksyncbot.xkz56cm.mongodb.net/?retryWrites=true&w=majority&appName=Zksyncbot")

# 👑 Admin
ADMIN_ID = 7428947778
OWNER_USERNAME = "@Vickonweb3"

# ⏰ Scheduler
TASK_INTERVAL_MINUTES = 90  # for random airdrop posts
SCRAPE_INTERVAL_HOURS = 3   # for scraping potential airdrops
