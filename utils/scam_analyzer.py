import requests
from retrying import retry
import sqlite3
import logging
import re
from datetime import datetime
import os

from dotenv import load_dotenv
load_dotenv()

SAFE_BROWSING_KEY = os.getenv("SAFE_BROWSING_KEY")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
WHOIS_API_KEY = os.getenv("WHOIS_API_KEY")
LUNAR_API_KEY = os.getenv("LUNAR_API_KEY")

logging.basicConfig(filename='zkdrop_scam.log', level=logging.ERROR)

conn = sqlite3.connect('zkdrop.db')
conn.execute('''CREATE TABLE IF NOT EXISTS scam_checks
                (link TEXT, contract TEXT, score INTEGER, timestamp TEXT)''')
cursor = conn.cursor()

@retry(stop_max_attempt_number=3, wait_fixed=3000)
def check_safe_browsing(url: str) -> int:
    try:
        response = requests.post(
            "https://safebrowsing.googleapis.com/v4/threatMatches:find",
            params={"key": SAFE_BROWSING_KEY},
            json={
                "client": {"clientId": "zkDrop", "clientVersion": "1.0"},
                "threatInfo": {
                    "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING"],
                    "platformTypes": ["ANY_PLATFORM"],
                    "threatEntryTypes": ["URL"],
                    "threatEntries": [{"url": url}]
                }
            }
        )
        response.raise_for_status()
        return 30 if response.json().get("matches") else 0
    except Exception as e:
        logging.error(f"Safe Browsing failed: {e}")
        scam_patterns = r"(metaamask|uniswop|claimnow|walletconnect|drainwallet)"
        return 20 if re.search(scam_patterns, url.lower()) else 0

@retry(stop_max_attempt_number=3, wait_fixed=3000)
def check_contract(address: str) -> int:
    score = 0
    try:
        r = requests.get(
            f"https://api.etherscan.io/api?module=contract&action=getsourcecode&address={address}&apikey={ETHERSCAN_API_KEY}"
        )
        data = r.json()["result"][0]
        if not data["SourceCode"]:
            score += 15

        r = requests.get(
            f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={ETHERSCAN_API_KEY}"
        )
        txs = r.json().get("result", [])
        if txs:
            creation_time = int(txs[0]["timeStamp"])
            days_old = (datetime.now().timestamp() - creation_time) / (3600 * 24)
            if days_old < 30:
                score += 10
    except Exception as e:
        logging.error(f"Etherscan check failed: {e}")
        score += 10

    return score

@retry(stop_max_attempt_number=3, wait_fixed=3000)
def check_domain_age(url: str) -> int:
    try:
        domain = re.findall(r"https?://([^/]+)", url)[0]
        response = requests.get(
            f"https://www.whoisxmlapi.com/whoisserver/WhoisService?apiKey={WHOIS_API_KEY}&domainName={domain}&outputFormat=JSON"
        )
        data = response.json()
        created = data["WhoisRecord"].get("createdDate")
        if created:
            created_date = datetime.strptime(created.split("T")[0], "%Y-%m-%d")
            days_old = (datetime.now() - created_date).days
            return 0 if days_old >= 30 else 20
        return 10
    except Exception as e:
        logging.error(f"WHOIS API check failed: {e}")
        return 10

@retry(stop_max_attempt_number=3, wait_fixed=3000)
def check_social_sentiment(token_symbol: str) -> int:
    try:
        response = requests.get(
            f"https://api.lunarcrush.com/v2?data=assets&key={LUNAR_API_KEY}&symbol={token_symbol}"
        )
        data = response.json()
        if not data.get("data"):
            return 10
        sentiment = data["data"][0].get("alt_rank", 100)
        if sentiment > 80:
            return 10
        elif sentiment < 30:
            return -5
        return 0
    except Exception as e:
        logging.error(f"LunarCrush sentiment check failed: {e}")
        return 5

def analyze_airdrop(link: str, contract: str = None, token_symbol: str = None) -> int:
    try:
        cached = cursor.execute("SELECT score FROM scam_checks WHERE link=? AND contract=?", (link, contract)).fetchone()
        if cached:
            return cached[0]

        score = 0
        score += check_safe_browsing(link)
        score += check_domain_age(link)

        if contract:
            score += check_contract(contract)

        if token_symbol:
            score += check_social_sentiment(token_symbol)

        cursor.execute("INSERT INTO scam_checks VALUES (?, ?, ?, ?)", (link, contract, score, datetime.now().isoformat()))
        conn.commit()

        return score
    except Exception as e:
        logging.error(f"Total scan failed: {e}")
        return 99
