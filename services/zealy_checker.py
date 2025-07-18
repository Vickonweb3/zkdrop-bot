import random
from datetime import datetime

# 🧠 Dummy Zealy quest data generator
def get_dummy_zealy_tasks():
    sample_tasks = [
        {"title": "Join Discord", "completed": True},
        {"title": "Follow on X", "completed": False},
        {"title": "Invite 3 friends", "completed": True},
        {"title": "Retweet pin post", "completed": False},
        {"title": "Connect wallet", "completed": True},
    ]
    random.shuffle(sample_tasks)
    return sample_tasks

# 📊 Fetch user's Zealy quest stats
def fetch_zealy_status(user_id: int):
    tasks = get_dummy_zealy_tasks()
    completed = sum(1 for task in tasks if task["completed"])
    total = len(tasks)

    response = f"📘 Zealy Task Summary for *User {user_id}*\n\n"
    for task in tasks:
        status = "✅" if task["completed"] else "❌"
        response += f"{status} {task['title']}\n"

    response += f"\n🏁 *Progress*: {completed}/{total} tasks completed"
    response += f"\n🕓 Updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"

    return response
