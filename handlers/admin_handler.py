from aiogram import types, Dispatcher
from config.settings import ADMIN_ID
from database.db import get_user_count, get_all_users
from services.zealy_checker import fetch_zealy_tasks

# 👑 Admin-only panel
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Access denied.")
        return

    text = (
        "👑 *Admin Panel*\n\n"
        "/stats - View bot stats\n"
        "/airdrops - Check airdrops manually\n"
        "/broadcast YourMessage - Send message to all users\n"
        "/reload - Restart acknowledgment"
    )
    await message.answer(text, parse_mode="Markdown")

# 📊 Stats
async def bot_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    count = get_user_count()
    await message.answer(f"📊 Total users: {count}")

# 🚀 Manual airdrop trigger
async def manual_airdrop_check(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    tasks = fetch_zealy_tasks()
    if not tasks:
        await message.answer("😕 No current airdrops found.")
    else:
        response = "📢 *Zealy Airdrops:*\n\n"
        for task in tasks:
            response += f"🔹 {task['title']} - [View]({task['link']})\n"
        await message.answer(response, parse_mode="Markdown", disable_web_page_preview=True)

# 📣 Broadcast
async def broadcast_message(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace('/broadcast ', '')
    users = get_all_users()
    success = 0
    for user_id in users:
        try:
            await message.bot.send_message(chat_id=user_id, text=text)
            success += 1
        except:
            continue
    await message.answer(f"✅ Sent to {success} users.")

# ♻️ Reload
async def reload_bot(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("♻️ Systems reloaded (mock).")

def register_admin(dp: Dispatcher):
    dp.register_message_handler(admin_panel, commands=['admin'])
    dp.register_message_handler(bot_stats, commands=['stats'])
    dp.register_message_handler(manual_airdrop_check, commands=['airdrops'])
    dp.register_message_handler(broadcast_message, commands=['broadcast'])
    dp.register_message_handler(reload_bot, commands=['reload'])
