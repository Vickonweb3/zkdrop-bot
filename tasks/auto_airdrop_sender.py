# tasks/auto_airdrop_sender.py

from utils.scam_analyzer import analyze_airdrop
from database.db import get_all_users
from aiogram import Bot
from config.settings import BOT_TOKEN
from utils.scam_filter import basic_scam_check

bot = Bot(token=BOT_TOKEN)

# 🔁 Dummy data source (replace with real scraper or API later)
airdrop_list = [
    {
        "project": "zkBase",
        "title": "zkToken Giveaway",
        "description": "Claim up to $50 in ZKB tokens now!",
        "link": "https://airdrop-zkbase.netlify.app",
        "contract": "0x000..."  # optional
    },
    # Add more airdrops here
]

async def auto_send_airdrops():
    for drop in airdrop_list:
        full_text = f"{drop['project']} {drop['title']} {drop['description']} {drop['link']}"
        score = analyze_airdrop(drop["link"], drop.get("contract"))
        
        if score < 30:
            msg = (
                f"🚀 *New Airdrop Alert!*\n\n"
                f"*Project:* {drop['project']}\n"
                f"*Title:* {drop['title']}\n"
                f"*Description:* {drop['description']}\n"
                f"*Link:* [Click here]({drop['link']})\n\n"
                f"🔁 Share with your friends & stay active!\n"
                f"#zkSync #airdrop"
            )
            users = await get_all_users()
            for user in users:
                try:
                    await bot.send_message(chat_id=user, text=msg, parse_mode="Markdown", disable_web_page_preview=True)
                except Exception:
                    continue
