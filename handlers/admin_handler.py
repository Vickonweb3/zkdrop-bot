from aiogram import types, Dispatcher
from config.settings import ADMIN_ID

# 👑 Admin-only command
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Access denied.")
        return

    text = (
        "👑 *Admin Panel*\n\n"
        "/stats - View bot stats\n"
        "/broadcast - Send message to all users (coming soon)\n"
        "/reload - Refresh bot systems (coming soon)"
    )
    await message.answer(text, parse_mode="Markdown")

def register_admin(dp: Dispatcher):
    dp.register_message_handler(admin_panel, commands=['admin'])
