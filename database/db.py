from pymongo import MongoClient
from config.settings import MONGO_URI, ADMIN_ID
from datetime import datetime
from bson.objectid import ObjectId

# ✅ Connect to MongoDB securely (Render-compatible)
client = MongoClient(
    MONGO_URI,
    tls=True,
    tlsAllowInvalidCertificates=True
)

db = client["zkdrop_bot"]

# ✅ Collections
users_collection = db["users"]
participants_collection = db["participants"]
airdrops_collection = db["airdrops"]

# ====================== 🧑 USER FUNCTIONS ======================

def save_user(user_id, username=None):
    if not users_collection.find_one({"user_id": user_id}):
        users_collection.insert_one({
            "user_id": user_id,
            "username": username,
            "joined_at": datetime.utcnow(),
            "banned": False
        })

def is_banned(user_id):
    user = users_collection.find_one({"user_id": user_id})
    return user and user.get("banned", False)

def ban_user(user_id):
    users_collection.update_one({"user_id": user_id}, {"$set": {"banned": True}})

def get_total_users():
    return users_collection.count_documents({})

def user_exists(user_id):
    return users_collection.find_one({"user_id": user_id}) is not None

def get_all_user_ids():
    return [user["user_id"] for user in users_collection.find({}, {"user_id": 1})]

get_all_users = get_all_user_ids
count_users = get_total_users

# ====================== 👥 PARTICIPANT FUNCTIONS ======================

def add_participant(user_id, community_id):
    participants_collection.update_one(
        {"user_id": user_id, "community_id": community_id},
        {"$setOnInsert": {
            "user_id": user_id,
            "community_id": community_id,
            "joined_at": datetime.utcnow()
        }},
        upsert=True
    )

def get_total_participants(community_id):
    return participants_collection.count_documents({"community_id": community_id})

# ====================== 🪂 AIRDROP FUNCTIONS ======================

def save_airdrop(platform, title, link):
    if not airdrops_collection.find_one({"link": link}):
        airdrops_collection.insert_one({
            "platform": platform,
            "title": title,
            "link": link,
            "timestamp": datetime.utcnow(),
            "posted": False  # Needed for /snipe
        })

def get_all_airdrop_links():
    return {doc["link"] for doc in airdrops_collection.find({}, {"link": 1})}

# ✅ Get one unposted airdrop (for snipe)
def get_unposted_airdrop():
    return airdrops_collection.find_one({"posted": False})

# ✅ Mark as posted after sniping
def mark_airdrop_posted(airdrop_id):
    airdrops_collection.update_one(
        {"_id": ObjectId(airdrop_id)},
        {"$set": {"posted": True}}
)
