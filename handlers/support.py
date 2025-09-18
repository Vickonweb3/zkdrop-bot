from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config.settings import ADMIN_ID
from datetime import datetime
from database.db import get_next_ticket_number, log_support_ticket, log_banned_user, remove_banned_user, get_banned_users  # optional DB helpers

router = Router()

# FSM States
class SupportStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_message = State()

# In-memory banned users (optional, or load from DB)
banned_users = set()

# Categories
CATEGORIES = ["Airdrop issue", "Bot issue", "Other"]

# ----------------------------
# Step 1: /support command
# ----------------------------
@router.message(commands=["support"])
async def start_support(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer("❌ You are currently restricted from submitting support tickets. Contact admin if this is a mistake.")
        return

    # Ask for category
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for cat in CATEGORIES:
        keyboard.add(cat)
    await message.answer("📝 Select a category for your support ticket:", reply_markup=keyboard)
    await state.set_state(SupportStates.waiting_for_category)

# ----------------------------
# Step 2: Receive category
# ----------------------------
@router.message(SupportStates.waiting_for_category)
async def receive_category(message: types.Message, state: FSMContext):
    category = message.text
    if category not in CATEGORIES:
        await message.answer("❌ Please select a valid category.")
        return

    await state.update_data(category=category)
    await message.answer("✏️ Please type your message for support.", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(SupportStates.waiting_for_message)

# ----------------------------
# Step 3: Receive user message
# ----------------------------
@router.message(SupportStates.waiting_for_message)
async def receive_support_message(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    category = user_data.get("category")
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    text = message.text

    # Generate ticket ID
    ticket_number = get_next_ticket_number()  # optional DB helper, or implement incrementing logic
    ticket_id = f"SB-{datetime.now().year}-{ticket_number:03d}"

    # Forward to admin
    support_msg = (
        f"📨 New Support Ticket\n"
        f"Ticket ID: {ticket_id}\n"
        f"User: {user_name} (ID: {user_id})\n"
        f"Category: {category}\n"
        f"Message:\n{text}\n"
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await message.bot.send_message(ADMIN_ID, support_msg)

    # Optional: Log ticket to DB
    log_support_ticket(ticket_id, user_id, user_name, category, text, status="Open")

    await message.answer(f"✅ Your ticket {ticket_id} has been submitted! We'll reply soon.")
    await state.clear()

# ----------------------------
# Step 4: Admin reply command
# Usage: /reply <ticket_id> <message>
# ----------------------------
@router.message(commands=["reply"])
async def admin_reply(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return  # Only admin can reply

    try:
        parts = message.text.split(maxsplit=2)
        ticket_id = parts[1]
        reply_text = parts[2]

        # Retrieve user ID from DB using ticket_id
        ticket = log_support_ticket.get_ticket(ticket_id)  # implement this in DB helper
        if not ticket:
            await message.answer("❌ Ticket ID not found.")
            return

        user_id = ticket["user_id"]
        await message.bot.send_message(user_id, f"💬 Reply from Support: {reply_text}")
        await message.answer(f"✅ Message sent to {user_id}")

        # Update ticket status
        log_support_ticket.update_status(ticket_id, "Replied")
    except:
        await message.answer("❌ Usage: /reply <ticket_id> <message>")

# ----------------------------
# Step 5: Ban / unban users
# ----------------------------
@router.message(commands=["ban"])
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(message.text.split()[1])
        banned_users.add(user_id)
        log_banned_user(user_id)  # optional DB log
        await message.answer(f"✅ User {user_id} has been banned from support.")
    except:
        await message.answer("❌ Usage: /ban <user_id>")

@router.message(commands=["unban"])
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    try:
        user_id = int(message.text.split()[1])
        banned_users.discard(user_id)
        remove_banned_user(user_id)  # optional DB
        await message.answer(f"✅ User {user_id} has been unbanned.")
    except:
        await message.answer("❌ Usage: /unban <user_id>")

# ----------------------------
# Step 6: List banned users
# ----------------------------
@router.message(commands=["banned"])
async def list_banned_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not banned_users:
        await message.answer("No users are currently banned.")
        return

    text = "🚫 Banned Users:\n"
    for uid in banned_users:
        text += f"- {uid}\n"
    await message.answer(text)
