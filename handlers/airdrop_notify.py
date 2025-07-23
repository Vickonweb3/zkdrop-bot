from aiogram import types, Router
from aiogram.exceptions import TelegramForbiddenError as BotBlocked
from aiogram.filters import Command  # ✅ Required in v3.x
from config.settings import ADMIN_ID
from utils.scam_filter import is_scam
from database.db import get_all_users

router = Router()  # ✅ Aiogram v3 style

# ✨ Format airdrop message
def format_airdrop(title, description, link, project):
    return (
        f"🚀 *New Airdrop Alert!*\n\n"
        f"*Project:* {project}\n"
        f"*Title:* {title}\n"
        f"*Description:* {description}\n"
        f"*Link:* [Click here]({link})\n\n"
        f"🔁 Share with your friends & stay active!\n"
        f"#zkSync #airdrop"
    )

# 🪂 Admin-only /airdrop command
@router.message(Command("airdrop"))
async def airdrop_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ You can't post airdrops.")
        return

    try:
        # Check for proper formatting
        if "|" not in message.text or message.text.count("|") != 3:
            raise ValueError("Incorrect format")

        # Parse input
        data = message.text.split(" ", 1)[1]
        project, title, description, link = [x.strip() for x in data.split("|")]

        # Scam check
        if is_scam(title + description + link + project):
            await message.answer("⚠️ This airdrop looks suspicious. Rejected.")
            return

        # Format and send message
        msg = format_airdrop(title, description, link, project)
        users = await get_all_users()

        count = 0
        for user_id in users:
            try:
                await message.bot.send_message(
                    user_id, msg, parse_mode="Markdown", disable_web_page_preview=True
                )
                count += 1
            except BotBlocked:
                continue

        await message.answer(f"✅ Airdrop sent to {count} users.")

    except Exception:
        await message.answer(
            "❌ Format error. Use:\n\n`/airdrop Project | Title | Description | Link`",
            parse_mode="Markdown"
        )

# 🔁 Scheduled airdrop sender (used by scheduler or webhook)
async def send_airdrop_to_all(bot, title, description, link, project):
    if is_scam(title + description + link + project):
        return

    msg = format_airdrop(title, description, link, project)
    users = await get_all_users()

    for user_id in users:
        try:
            await bot.send_message(
                user_id, msg, parse_mode="Markdown", disable_web_page_preview=True
            )
        except BotBlocked:
            continue
