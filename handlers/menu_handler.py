from aiogram import types, Router, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config.settings import OWNER_USERNAME, ADMIN_ID  # make sure ADMIN_ID is added in settings

router = Router()

# Simulated real stats
REAL_USER_COUNT = 3  # Replace with DB call later
DISPLAY_USER_COUNT = "4,900+"
AIRDROP_LIST = (
    "🧬 *zkSync Quest* – Do tasks, earn points\n"
    "🌊 *Manta Faucet* – Get testnet tokens\n"
    "⚡ *LayerZero Tasks* – Early support actions\n"
    "🚀 *Starknet Claim* – Stay ready for drop"
)

# 🎛️ /menu command handler
@router.message(F.text == "/menu")
async def show_main_menu(message: types.Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Airdrops", callback_data="airdrops"),
                InlineKeyboardButton(text="📊 Stats", callback_data="stats"),
            ],
            [
                InlineKeyboardButton(
                    text="📎 Follow Us on X",
                    url=f"https://x.com/{OWNER_USERNAME.replace('@', '')}"
                ),
                InlineKeyboardButton(text="💬 Contact Dev", url="https://t.me/Vickonweb3"),
            ]
        ]
    )

    await message.answer(
        "📍 *Main Menu* — choose an option:",
        reply_markup=kb,
        parse_mode="Markdown"
    )

# 🤖 Callback Query Handler
@router.callback_query()
async def handle_menu_callback(call: types.CallbackQuery):
    if call.data == "airdrops":
        await call.message.edit_text(
            f"🚀 *Latest Airdrops:*\n\n{AIRDROP_LIST}",
            parse_mode="Markdown"
        )
    elif call.data == "stats":
        # Show real count to admin only
        user_count = str(REAL_USER_COUNT) if str(call.from_user.id) == str(ADMIN_ID) else DISPLAY_USER_COUNT
        await call.message.edit_text(
            f"📊 Users Registered: *{user_count}*\n"
            f"Airdrops Tracked: *4*",
            parse_mode="Markdown"
        )
    else:
        await call.message.answer("❌ Unknown option.")
