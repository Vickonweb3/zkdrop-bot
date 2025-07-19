from pymongo import MongoClient
from config.settings import MONGO_URI
from datetime import datetime  # <== You also forgot to import this!

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client["zkdrop_bot"]

# Collections
users_collection = db["users"]

# 🔘 Save user to database
def save_user(user_id, username=None):  # Renamed from add_user
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({
            "user_id": user_id,
            "username": username,
            "joined_at": datetime.utcnow()
        })

# 🧾 Get total users count
def get_total_users():
    return users_collection.count_documents({})

# 🔎 Check if user exists
def user_exists(user_id):
    return users_collection.find_one({"user_id": user_id}) is not None

# 📤 Get all user IDs (for broadcasting)
def get_all_user_ids():
    return [user["user_id"] for user in users_collection.find({}, {"user_id": 1})]
