from aiogram import types, Dispatcher
from config.settings import OWNER_USERNAME
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


# 🎛️ /menu command handler
async def show_menu(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=2)

    kb.add(
        InlineKeyboardButton("📢 Airdrops", callback_data="airdrops"),
        InlineKeyboardButton("📊 Stats", callback_data="stats"),
    )
    kb.add(
        InlineKeyboardButton("📎 Follow Us on X", url=f"https://x.com/{OWNER_USERNAME.replace('@', '')}"),
        InlineKeyboardButton("💬 Contact Dev", url="https://t.me/Vickonweb3"),
    )

    await message.answer("📍 *Main Menu* — choose an option:", reply_markup=kb, parse_mode="Markdown")


# 🤖 Callback Query Handler
async def handle_menu_callback(call: types.CallbackQuery):
    if call.data == "airdrops":
        await call.message.edit_text("🚀 Latest airdrops will be listed here soon (auto updates coming).")
    elif call.data == "stats":
        await call.message.edit_text("📊 Users Registered: *loading...*\nAirdrops Tracked: *loading...*", parse_mode="Markdown")
    else:
        await call.message.answer("❌ Unknown option.")


def register_menu(dp: Dispatcher):
    dp.register_message_handler(show_menu, commands=["menu"])
    dp.register_callback_query_handler(handle_menu_callback)
