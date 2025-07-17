from aiogram import types, Dispatcher
from config.settings import OWNER_USERNAME

async def start_command(message: types.Message):
    welcome_text = (
        "🚀 *Welcome to ZKDrop Bot!*\n\n"
        "I'm your guide to discovering new airdrops and reward campaigns (Zealy & more).\n\n"
        "🔗 *To get started:* \n"
        "1. Make sure to follow us on [X (Twitter)](https://twitter.com/VickOnWeb3)\n"
        "2. Then come back here and type /menu to view tasks and updates.\n\n"
        f"👨‍💻 Need help? Contact dev: {OWNER_USERNAME}"
    )
    await message.answer(welcome_text, parse_mode="Markdown", disable_web_page_preview=True)

def register_start(dp: Dispatcher):
    dp.register_message_handler(start_command, commands=["start"])
