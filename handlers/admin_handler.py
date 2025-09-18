from aiogram import types, Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config.settings import ADMIN_ID
from database.db import (
    count_users,
    get_total_participants,
    get_unposted_airdrop,
    mark_airdrop_posted,
    airdrops_collection,
    participants_collection,
    get_all_user_ids
)
from utils.twitter_rating import rate_twitter_buzz
import asyncio

router = Router()

# ==========================
#   ADMIN UTILITIES
# ==========================

# Support multiple admins: ADMIN_ID = "123,456"
ADMIN_IDS = [aid.strip() for aid in str(ADMIN_ID).split(",")]

def is_admin(user_id):
    return str(user_id) in ADMIN_IDS


# ==========================
#   STATES
# ==========================

class BroadcastStates(StatesGroup):
    waiting_for_message = State()


# ==========================
#   COMMANDS
# ==========================

# 📊 /stats command
@router.message(Command("stats"))
async def view_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Access denied.")

    user_count = count_users()
    airdrop_count = airdrops_collection.count_documents({})
    participants_count = participants_collection.count_documents({})

    text = (
        "📊 *Bot Stats*\n\n"
        f"👥 Total Users: *{user_count}*\n"
        f"🪂 Airdrops Saved: *{airdrop_count}*\n"
        f"👥 Participants Tracked: *{participants_count}*\n"
        "📡 System Status: *Online*\n"
        "📅 Scheduler: *Active*\n"
    )
    await message.answer(text, parse_mode="Markdown")


# 📣 /broadcast command
@router.message(Command("broadcast"))
async def broadcast(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Access denied.")

    await message.answer(
        "📣 Send me the message (any format: text, photo, video, etc.) you want to broadcast.\n\n"
        "💡 Or use /suggest to see ready-made templates."
    )
    await state.set_state(BroadcastStates.waiting_for_message)


# 🎯 Handle broadcast content
@router.message(BroadcastStates.waiting_for_message)
async def handle_broadcast(msg: types.Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return

    user_ids = get_all_user_ids()
    sent_count, failed_count = 0, 0

    for uid in user_ids:
        try:
            await msg.bot.copy_message(
                chat_id=uid,
                from_chat_id=msg.chat.id,
                message_id=msg.message_id
            )
            sent_count += 1
            await asyncio.sleep(0.05)  # rate limit
        except Exception:
            failed_count += 1
            continue

    await msg.answer(
        f"✅ Broadcast complete!\n\n"
        f"📤 Sent: *{sent_count}*\n"
        f"⚠️ Failed: *{failed_count}*",
        parse_mode="Markdown"
    )
    await state.clear()


# 💡 /suggest command (quick templates for broadcast)
@router.message(Command("suggest"))
async def suggest_templates(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Access denied.")

    builder = InlineKeyboardBuilder()
    builder.button(text="🌞 Good Morning Update", callback_data="tpl:morning")
    builder.button(text="🚀 New Airdrop Alert", callback_data="tpl:airdrop")
    builder.button(text="⏰ Reminder", callback_data="tpl:reminder")
    builder.button(text="📢 General Update", callback_data="tpl:update")
    builder.adjust(1)

    await message.answer(
        "💡 Choose a template to broadcast:",
        reply_markup=builder.as_markup()
    )


# 🎯 Handle template selection
@router.callback_query(F.data.startswith("tpl:"))
async def handle_template_callback(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("⛔ Access denied.", show_alert=True)

    template_map = {
        "tpl:morning": "🌞 Good morning everyone! Wishing you a productive day ahead 🚀",
        "tpl:airdrop": "🚀 *New Airdrop Alert!*\n\nCheck the bot menu now to claim before it ends!",
        "tpl:reminder": "⏰ Reminder: Don’t forget to complete your daily quests and claim rewards!",
        "tpl:update": "📢 Update: Stay tuned for new features and campaigns coming soon 🔥"
    }

    tpl = template_map.get(callback.data, "📢 General update from admin.")

    user_ids = get_all_user_ids()
    sent_count, failed_count = 0, 0

    for uid in user_ids:
        try:
            await callback.bot.send_message(uid, tpl, parse_mode="Markdown")
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed_count += 1
            continue

    await callback.message.answer(
        f"✅ Template broadcast complete!\n\n"
        f"📤 Sent: *{sent_count}*\n"
        f"⚠️ Failed: *{failed_count}*",
        parse_mode="Markdown"
    )
    await callback.answer("✅ Broadcast sent!")


# 👥 /users command (show sample users)
@router.message(Command("users"))
async def list_users(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Access denied.")

    user_ids = get_all_user_ids()
    sample = user_ids[:20]  # show first 20 users
    text = "👥 *Registered Users (sample)*:\n\n" + "\n".join(map(str, sample))
    text += f"\n\n📊 Total users: *{len(user_ids)}*"

    await message.answer(text, parse_mode="Markdown")


# 🔁 /reload command
@router.message(Command("reload"))
async def reload_bot(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Access denied.")

    await message.answer("🔄 Bot systems reloaded (simulated).")


# 👥 /participants <community_id>
@router.message(Command("participants"))
async def participants_command(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Access denied.")

    parts = message.text.strip().split()
    if len(parts) != 2:
        return await message.reply("❌ Usage: /participants <community_id>")

    community_id = parts[1]
    total = get_total_participants(community_id)

    await message.reply(
        f"👥 Total participants in *{community_id}*: *{total}*",
        parse_mode="Markdown"
    )


# 🔫 /snipe command
@router.message(Command("snipe"))
async def snipe_airdrop(message: types.Message):
    if not is_admin(message.from_user.id):
        return await message.answer("⛔ Access denied.")

    airdrop = get_unposted_airdrop()
    if not airdrop:
        return await message.answer("🕵️ No new airdrops found.")

    buzz = rate_twitter_buzz(airdrop.get("twitter_url", ""))
    caption = f"""
🚀 *New Airdrop Detected* 🚀

🔹 *Project:* {airdrop.get('project_name', 'Unknown')}
🌐 *Website:* {airdrop.get('project_link', 'N/A')}
🐦 *Twitter:* {airdrop.get('twitter_url', 'N/A')}
🔥 *Buzz Rating:* {buzz}/10

⏳ Claim it before it's gone!
"""

    await message.answer(caption, parse_mode="Markdown")
    mark_airdrop_posted(airdrop["_id"])
    await message.answer("✅ Airdrop sniped and shared successfully.", parse_mode="Markdown")


# 🔌 Register all admin commands
def register_admin(dp):
    dp.include_router(router)
