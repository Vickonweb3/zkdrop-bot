from aiogram import types
from aiogram.dispatcher import Dispatcher
from database.db import save_airdrop_to_db

def register_notify(dp: Dispatcher):
    @dp.message_handler(commands=["airdrops"])
    async def send_airdrop(message: types.Message):
        example_airdrop = {
            "title": "🔵 zkSync Airdrop Opportunity!",
            "description": "Earn rewards by completing Zealy quests. 🔗 [Join Zealy](https://zealy.io/c/zkdrop)",
            "requirements": "- Connect wallet\n- Complete tasks\n- Invite friends",
            "reward": "$50+ in tokens",
        }

        await message.answer(
            f"*{example_airdrop['title']}*\n\n"
            f"{example_airdrop['description']}\n\n"
            f"*Requirements:*\n{example_airdrop['requirements']}\n\n"
            f"💰 *Estimated Reward:* {example_airdrop['reward']}",
            parse_mode="Markdown",
            disable_web_page_preview=False
        )

        await save_airdrop_to_db(example_airdrop)
