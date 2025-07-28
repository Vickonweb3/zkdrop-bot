from aiogram import types, Router
from aiogram.exceptions import TelegramForbiddenError as BotBlocked
from aiogram.filters import Command
from config.settings import ADMIN_ID
from utils.scam_filter import is_scam
from database.db import get_all_users

router = Router()

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
        if "|" not in message.text or message.text.count("|") != 3:
            raise ValueError("Incorrect format")

        data = message.text.split(" ", 1)[1]
        project, title, description, link = [x.strip() for x in data.split("|")]

        if is_scam(f"{project} {title} {description} {link}"):
            await message.answer("⚠️ This airdrop looks suspicious. Rejected.")
            return

        msg = format_airdrop(title, description, link, project)
        users = await get_all_users()

        count = 0
        for user_id in users:
            try:
                await message.bot.send_message(
                    chat_id=user_id,
                    text=msg,
                    parse_mode="Markdown",
                    disable_web_page_preview=True
                )
                count += 1
            except BotBlocked:
                continue
            except Exception as e:
                print(f"❌ Failed to send to {user_id}: {e}")
                continue

        await message.answer(f"✅ Airdrop sent to {count} users.")

    except Exception as e:
        await message.answer(
            "❌ Format error. Use:\n\n`/airdrop Project | Title | Description | Link`",
            parse_mode="Markdown"
        )
        print(f"❌ Airdrop command error: {e}")

# 🔁 Scheduled airdrop sender (used by scheduler/webhook)
async def send_airdrop_to_all(bot, title, description, link, project):
    if is_scam(f"{project} {title} {description} {link}"):
        return

    msg = format_airdrop(title, description, link, project)
    users = await get_all_users()

    for user_id in users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except BotBlocked:
            continue
        except Exception as e:
            print(f"❌ Failed to send to {user_id}: {e}")
            continue
