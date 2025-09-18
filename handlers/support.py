import logging
from aiogram import types, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from config.settings import ADMIN_ID
from datetime import datetime

# ----------------------------
# Logger setup
# ----------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ----------------------------
# Router
# ----------------------------
router = Router()

# ----------------------------
# FSM States
# ----------------------------
class SupportStates(StatesGroup):
    waiting_for_category = State()
    waiting_for_message = State()

CATEGORIES = ["Airdrop issue", "Bot issue", "Other"]

# ----------------------------
# Collections (to be injected from main.py)
# ----------------------------
tickets_collection = None
banned_collection = None

def setup_collections(tickets, banned):
    """Inject MongoDB collections from main.py to avoid circular imports."""
    global tickets_collection, banned_collection
    tickets_collection = tickets
    banned_collection = banned

# ----------------------------
# Helper functions
# ----------------------------
def get_next_ticket_number():
    last_ticket = tickets_collection.find_one(sort=[("ticket_number", -1)])
    return (last_ticket["ticket_number"] + 1) if last_ticket else 1

def log_support_ticket(ticket_id, user_id, username, category, message, status="Open"):
    ticket_number = int(ticket_id.split("-")[-1])
    tickets_collection.insert_one({
        "ticket_id": ticket_id,
        "ticket_number": ticket_number,
        "user_id": user_id,
        "username": username,
        "category": category,
        "message": message,
        "status": status,
        "timestamp": datetime.utcnow()
    })

def get_ticket(ticket_id):
    return tickets_collection.find_one({"ticket_id": ticket_id})

def update_ticket_status(ticket_id, status):
    tickets_collection.update_one({"ticket_id": ticket_id}, {"$set": {"status": status}})

def log_banned_user(user_id):
    banned_collection.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

def remove_banned_user(user_id):
    banned_collection.delete_one({"user_id": user_id})

def get_banned_users():
    return [doc["user_id"] for doc in banned_collection.find()]

# ----------------------------
# Handlers
# ----------------------------
@router.message(Command(commands=["support"]))
async def start_support(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in get_banned_users():
        await message.answer("❌ You are restricted from submitting support tickets.")
        return

    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for cat in CATEGORIES:
        keyboard.add(cat)
    await message.answer("📝 Select a category for your support ticket:", reply_markup=keyboard)
    await state.set_state(SupportStates.waiting_for_category)

@router.message(SupportStates.waiting_for_category)
async def receive_category(message: types.Message, state: FSMContext):
    category = message.text
    if category not in CATEGORIES:
        await message.answer("❌ Please select a valid category.")
        return

    await state.update_data(category=category)
    await message.answer("✏️ Type your support message:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(SupportStates.waiting_for_message)

@router.message(SupportStates.waiting_for_message)
async def receive_support_message(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    category = user_data.get("category")
    user_id = message.from_user.id
    user_name = message.from_user.full_name
    text = message.text

    ticket_number = get_next_ticket_number()
    ticket_id = f"SB-{datetime.utcnow().year}-{ticket_number:03d}"

    support_msg = (
        f"📨 New Support Ticket\n"
        f"Ticket ID: {ticket_id}\n"
        f"User: {user_name} (ID: {user_id})\n"
        f"Category: {category}\n"
        f"Message:\n{text}\n"
        f"Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
    )
    try:
        await message.bot.send_message(ADMIN_ID, support_msg)
    except Exception as e:
        logger.exception(f"Failed to send ticket {ticket_id} to admin: {e}")

    log_support_ticket(ticket_id, user_id, user_name, category, text)
    await message.answer(f"✅ Your ticket {ticket_id} has been submitted! We'll reply soon.")
    await state.clear()

# ----------------------------
# Admin commands
# ----------------------------
@router.message(Command(commands=["reply"]))
async def admin_reply(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        parts = message.text.split(maxsplit=2)
        ticket_id, reply_text = parts[1], parts[2]
    except IndexError:
        await message.answer("❌ Usage: /reply <ticket_id> <message>")
        return

    ticket = get_ticket(ticket_id)
    if not ticket:
        await message.answer("❌ Ticket not found.")
        return

    user_id = ticket["user_id"]
    try:
        await message.bot.send_message(user_id, f"💬 Reply from Support: {reply_text}")
        await message.answer(f"✅ Message sent to {user_id}")
        update_ticket_status(ticket_id, "Replied")
    except Exception as e:
        logger.exception(f"Failed to reply to ticket {ticket_id}: {e}")
        await message.answer("❌ Failed to send message to user.")

@router.message(Command(commands=["ban"]))
async def ban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        log_banned_user(user_id)
        await message.answer(f"✅ User {user_id} banned from support.")
    except:
        await message.answer("❌ Usage: /ban <user_id>")

@router.message(Command(commands=["unban"]))
async def unban_user(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        remove_banned_user(user_id)
        await message.answer(f"✅ User {user_id} unbanned from support.")
    except:
        await message.answer("❌ Usage: /unban <user_id>")

@router.message(Command(commands=["banned"]))
async def list_banned_users(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    banned_list = get_banned_users()
    if not banned_list:
        await message.answer("No users are banned.")
        return
    text = "🚫 Banned Users:\n" + "\n".join(f"- {uid}" for uid in banned_list)
    await message.answer(text)
