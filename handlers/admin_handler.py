from aiogram import types, Dispatcher
from config.settings import ADMIN_ID
from database.db import count_users
from aiogram.utils.markdown import bold

# 🛡️ Admin-only checker
def is_admin(user_id):
    return user_id == ADMIN_ID

# 📊 /stats command
async def view_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    user_count = await count_users()
    text = (
        "📊 *Bot Stats*\n\n"
        f"👥 Total Users: *{user_count}*\n"
        "📡 System Status: *Online*\n"
        "📅 Scheduler: *Active*\n"
    )
    await message.answer(text, parse_mode="Markdown")

# 📣 /broadcast command (placeholder to activate later)
async def broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    await message.answer("📣 Broadcast feature will be added in Phase 2.")

# 🔁 /reload command
async def reload_bot(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    await message.answer("🔄 Bot systems reloaded (simulated).")

# 📍 Register admin commands
def register_admin(dp: Dispatcher):
    dp.register_message_handler(view_stats, commands=["stats"])
    dp.register_message_handler(broadcast, commands=["broadcast"])
    dp.register_message_handler(reload_bot, commands=["reload"])
