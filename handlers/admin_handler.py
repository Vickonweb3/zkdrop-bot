from aiogram import types, Router
from aiogram.filters import Command
from config.settings import ADMIN_ID
from database.db import count_users, get_total_participants, get_unposted_airdrop, mark_airdrop_posted
from utils.twitter_rating import rate_twitter_buzz

router = Router()

# 🛡️ Admin-only checker
def is_admin(user_id):
    return str(user_id) == str(ADMIN_ID)

# 📊 /stats command
@router.message(Command("stats"))
async def view_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    user_count = count_users()
    text = (
        "📊 *Bot Stats*\n\n"
        f"👥 Total Users: *{user_count}*\n"
        "📡 System Status: *Online*\n"
        "📅 Scheduler: *Active*\n"
    )
    await message.answer(text, parse_mode="Markdown")

# 📣 /broadcast command (placeholder to activate later)
@router.message(Command("broadcast"))
async def broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    await message.answer("📣 Broadcast feature will be added in Phase 2.")

# 🔁 /reload command
@router.message(Command("reload"))
async def reload_bot(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    await message.answer("🔄 Bot systems reloaded (simulated).")

# 👥 /participants <community_id>
@router.message(Command("participants"))
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

# 🔫 /snipe command — get latest airdrop and send it to admin
@router.message(Command("snipe"))
async def snipe_airdrop(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Access denied.")
        return

    airdrop = get_unposted_airdrop()
    if not airdrop:
        await message.answer("🕵️ No new airdrops found.")
        return

    # 🧠 Rate using Twitter
    buzz = rate_twitter_buzz(airdrop["twitter_url"])
    caption = f"""
🚀 *New Airdrop Detected* 🚀

🔹 *Project:* {airdrop['project_name']}
🌐 *Website:* {airdrop['project_link']}
🐦 *Twitter:* {airdrop['twitter_url']}
🔥 *Buzz Rating:* {buzz}/10

⏳ Claim it before it's gone!
"""

    # ✅ Send it to admin instead of a group
    await message.answer(caption, parse_mode="Markdown")

    # ✅ Mark as posted
    mark_airdrop_posted(airdrop["_id"])

    await message.answer("✅ Airdrop sniped and shared successfully.", parse_mode="Markdown")

# 🔌 Register all admin commands
def register_admin(dp):
    dp.include_router(router)
