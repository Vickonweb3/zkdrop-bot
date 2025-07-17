from aiogram import types, Dispatcher
from utils.scraper import fetch_latest_airdrops
from utils.scam_filter import is_scam

# 🛸 Notify users about new airdrops
async def notify_airdrops(message: types.Message):
    airdrops = fetch_latest_airdrops()
    for drop in airdrops:
        if not is_scam(drop):
            await message.answer(f"🚀 *New Airdrop Alert!*\n\n{drop}", parse_mode="Markdown")

def register_notify(dp: Dispatcher):
    dp.register_message_handler(notify_airdrops, commands=['airdrops'])
