from aiogram import Dispatcher
from aiogram.types import Message
from services.zealy_checker import fetch_zealy_tasks
from utils.scam_filter import is_scammy
from database.db import get_all_users
from config.settings import ADMIN_ID

# 📢 Function to notify all users about new airdrops
async def notify_users(bot):
    tasks = fetch_zealy_tasks()
    if not tasks:
        return

    for task in tasks:
        if is_scammy(task["title"]):
            continue  # Skip scammy or duplicate-looking tasks

        text = f"🚀 *New Airdrop Opportunity!*\n\n🔸 {task['title']}\n🔗 [Join Airdrop]({task['link']})"
        users = get_all_users()
        for user_id in users:
            try:
                await bot.send_message(chat_id=user_id, text=text, parse_mode="Markdown", disable_web_page_preview=True)
            except:
                continue  # Skip failed messages

# Optional: Message-based trigger (used only for manual test, not required)
async def notify_test(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await notify_users(message.bot)
    await message.answer("✅ Airdrop notifications sent.")

def register_notify(dp: Dispatcher):
    dp.register_message_handler(notify_test, commands=['notify'])
