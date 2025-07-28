import os
from dotenv import load_dotenv

# 📦 Load environment variables
load_dotenv(dotenv_path="resr/.env")  # adjust if your .env path is different

# 🔐 Secure credentials
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

# 👑 Admin config
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@YourUsername")

# ⏰ Scheduler intervals
TASK_INTERVAL_MINUTES = int(os.getenv("TASK_INTERVAL_MINUTES", 16))  # how often to send airdrops
SCRAPE_INTERVAL_HOURS = int(os.getenv("SCRAPE_INTERVAL_HOURS", 1))   # how often to scrape new airdrops
