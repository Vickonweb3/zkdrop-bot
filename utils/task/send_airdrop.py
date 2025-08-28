from database.db import get_all_users
from utils.scam_filter import basic_scam_check  # ✅ Fixed import
from aiogram.exceptions import TelegramForbiddenError as BotBlocked

# ✅ Format the airdrop message (kept for fallback/manual sends)
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

# 🔁 Auto-send to all users
async def send_airdrop_to_all(bot, title, description, link, project, preformatted: bool = False):
    """
    Send airdrop to all users.
    If `preformatted=True`, then `description` is treated as a full message.
    Otherwise, it will be formatted with format_airdrop().
    """
    # Basic scam check
    if basic_scam_check(f"{project} {title} {description} {link}"):
        return

    # Decide message format
    if preformatted:
        msg = description  # already a complete message (from scheduler)
    else:
        msg = format_airdrop(title, description, link, project)

    # Broadcast
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
