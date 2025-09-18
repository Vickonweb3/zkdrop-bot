# utils/users.py
from datetime import datetime
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["zkdrop_bot"]   # your database name
users_col = db["users"]     # collection for users

def save_user(user_id: int, username: str, first_name: str):
    """Save user if not already saved"""
    if not users_col.find_one({"user_id": user_id}):
        users_col.insert_one({
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "joined_at": datetime.utcnow()
        })

def get_all_users():
    """Return all users in DB"""
    return list(users_col.find({}))

def remove_user(user_id: int):
    """Remove user if they block the bot"""
    users_col.delete_one({"user_id": user_id})
