import logging
from aiogram import Bot
from config.settings import ADMIN_ID

# ✅ Send airdrop message (currently to admin only)
async def send_airdrop_to_main_group(bot: Bot, text: str):
    try:
        await bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown", disable_web_page_preview=False)
    except Exception as e:
        logging.error(f"❌ Failed to send airdrop: {e}")
