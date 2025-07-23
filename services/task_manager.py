# Legends 

from aiogram import types
from database.db import add_participant

# 🧠 Simulate task verification + record user as participant
async def handle_task_verification(message: types.Message):
    user_id = message.from_user.id
    community_id = "zkcrew123"  # You can make this dynamic later

    # Add the user as a participant
    add_participant(user_id, community_id)

    await message.answer(
        f"✅ Task verified!\n\nYou’ve been added as a participant in *{community_id}*.",
        parse_mode="Markdown"
    )
