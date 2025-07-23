from aiogram import types, Router
from config.settings import OWNER_USERNAME
from handlers.menu_handler import show_main_menu
from database.db import save_user, is_banned

router = Router()

# 🚀 Start command
@router.message(commands=["start"])
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"

    # ❌ Banned users
    if is_banned(user_id):  # Also remove 'await' if it's a sync function
        await message.answer("⛔ You are banned from using this bot.")
        return

    # ✅ Save to database
    save_user(user_id, username)

    # 📣 Welcome message
    welcome_text = (
        "🌐 *Welcome to zkDrop Bot!*\n\n"
        "🤖 I'm your Web3 sidekick. I’ll alert you to fresh zkSync tasks, Zealy campaigns, and more.\n\n"
        "🐦 *Step 1:* Follow us on Twitter: [@VickOnWeb3](https://twitter.com/VickOnWeb3)\n"
        "📲 *Step 2:* Explore tasks using the menu below.\n\n"
        f"🆘 For support, contact {OWNER_USERNAME}"
    )

    await message.answer(welcome_text, parse_mode="Markdown", disable_web_page_preview=True)

    # 📲 Show main menu
    await show_main_menu(message)

# 🔌 Register router
def register_start(dp):
    dp.include_router(router)
