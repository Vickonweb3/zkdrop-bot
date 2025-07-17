from aiogram import types
from aiogram.dispatcher import Dispatcher
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def register_menu(dp: Dispatcher):
    @dp.message_handler(commands=["menu"])
    async def send_menu(message: types.Message):
        keyboard = InlineKeyboardMarkup(row_width=2)
        
        keyboard.add(
            InlineKeyboardButton(text="📢 Latest Airdrops", callback_data="view_airdrops"),
            InlineKeyboardButton(text="✅ Tasks Completed", callback_data="view_tasks"),
            InlineKeyboardButton(text="⚙️ Account Settings", callback_data="settings"),
            InlineKeyboardButton(text="❓ Help", callback_data="help"),
        )

        await message.answer(
            "📍 *Main Menu*\nChoose an option below to get started:",
            reply_markup=keyboard,
            parse_mode="Markdown"
  )
