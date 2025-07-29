import logging
from database.db import get_all_users
from utils.scam_analyzer import basic_scam_check
from utils.twitter_rating import rate_twitter_buzz

# 🪙 Format airdrop message
def format_airdrop(project, title, description, link, buzz_score=None):
    buzz_text = f"\n🔥 Twitter Buzz: {buzz_score}/10" if buzz_score else ""
    return (
        f"🚀 *New Airdrop Detected!*\n\n"
        f"*Project:* {project}\n"
        f"*Title:* {title}\n"
        f"*Description:* {description}\n"
        f"*Link:* {link}"
        f"{buzz_text}\n\n"
        f"🔁 Share and stay active!"
    )

# 🛰️ Send airdrop to all users
async def send_auto_airdrop(bot, project, title, description, link, twitter_url=""):
    # Scam Check
    if basic_scam_check(f"{project} {title} {description} {link}"):
        logging.warning("⚠️ Scam detected. Drop rejected.")
        return

    # Buzz Score (optional)
    try:
        buzz_score = rate_twitter_buzz(twitter_url) if twitter_url else None
    except Exception as e:
        logging.warning(f"⚠️ Buzz score error: {e}")
        buzz_score = None

    # Message
    msg = format_airdrop(project, title, description, link, buzz_score)

    # Users
    users = await get_all_users()
    success = 0
    for user_id in users:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            success += 1
        except Exception as e:
            logging.warning(f"❌ Failed for {user_id}: {e}")
            continue

    logging.info(f"✅ Airdrop sent to {success}/{len(users)} users.")
