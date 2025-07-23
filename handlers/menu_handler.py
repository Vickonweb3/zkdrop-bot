from aiogram import types, Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config.settings import OWNER_USERNAME

router = Router()

# 🎛️ /menu command handler
@router.message(F.text == "/menu")
async def show_main_menu(message: types.Message):
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
@router.callback_query()
async def handle_menu_callback(call: types.CallbackQuery):
    if call.data == "airdrops":
        await call.message.edit_text("🚀 Latest airdrops will be listed here soon (auto updates coming).")
    elif call.data == "stats":
        await call.message.edit_text(
            "📊 Users Registered: *loading...*\nAirdrops Tracked: *loading...*",
            parse_mode="Markdown"
        )
    else:
        await call.message.answer("❌ Unknown option.")

# 📌 Register router into dispatcher
def register_menu(dp):
    dp.include_router(router)
