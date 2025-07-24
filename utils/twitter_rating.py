import requests
import os
import logging

BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

def rate_twitter_buzz(tweet_url):
    try:
        # Extract tweet ID from URL
        tweet_id = tweet_url.split("/")[-1].split("?")[0]

        # Twitter API v2 endpoint
        url = f"https://api.twitter.com/2/tweets/{tweet_id}?tweet.fields=public_metrics"

        headers = {
            "Authorization": f"Bearer {BEARER_TOKEN}"
        }

        response = requests.get(url, headers=headers)
        data = response.json()

        if "data" not in data or "public_metrics" not in data["data"]:
            return "⚠️ Rating unavailable"

        metrics = data["data"]["public_metrics"]
        likes = metrics.get("like_count", 0)
        retweets = metrics.get("retweet_count", 0)
        replies = metrics.get("reply_count", 0)

        # Simple score (you can tweak this)
        score = likes + (retweets * 2) + replies

        # Rating level
        if score > 2000:
            level = "🔥 Viral"
        elif score > 500:
            level = "🚀 Trending"
        elif score > 100:
            level = "🌟 Active"
        else:
            level = "🧊 Low Buzz"

        return f"{level} ({score} buzz score)"

    except Exception as e:
        logging.error(f"Twitter rating error: {e}")
        return "⚠️ Rating unavailable"
