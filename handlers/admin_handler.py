from aiogram import types, Dispatcher
from config.settings import ADMIN_ID
from database.db import count_users, get_total_participants
from aiogram.utils.markdown import bold

# 🛡️ Admin-only checker
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# 📊 /stats command
async def view_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    user_count = count_users()  # No await needed
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

# 👥 /participants <community_id>
async def participants_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.reply("❌ Usage: /participants <community_id>")
        return

    community_id = parts[1]
    total = get_total_participants(community_id)

    await message.reply(
        f"👥 Total participants in *{community_id}*: *{total}*",
        parse_mode="Markdown"
    )

# 📍 Register all admin commands
def register_admin(dp: Dispatcher):
    dp.register_message_handler(view_stats, commands=["stats"])
    dp.register_message_handler(broadcast, commands=["broadcast"])
    dp.register_message_handler(reload_bot, commands=["reload"])
    dp.register_message_handler(participants_command, commands=["participants"])
