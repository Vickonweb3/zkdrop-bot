import requests
from retrying import retry
import whois
import sqlite3
import logging
import re
from datetime import datetime
import os

# Load from .env (optional)
from dotenv import load_dotenv
load_dotenv()

SAFE_BROWSING_KEY = os.getenv("SAFE_BROWSING_API")
ETHERSCAN_KEY = os.getenv("ETHERSCAN_API")

# 🚨 Setup logging
logging.basicConfig(filename='zkdrop_scam.log', level=logging.ERROR)

# ✅ Connect to SQLite (basic cache to avoid repeated checks)
conn = sqlite3.connect('zkdrop.db')
conn.execute('''CREATE TABLE IF NOT EXISTS scam_checks
                (link TEXT, contract TEXT, score INTEGER, timestamp TEXT)''')
cursor = conn.cursor()

# 🔍 Google Safe Browsing or fallback regex
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

# 🔍 Check smart contract audit status and creation time
@retry(stop_max_attempt_number=3, wait_fixed=3000)
def check_contract(address: str) -> int:
    score = 0
    try:
        # Get contract source
        r = requests.get(
            f"https://api.etherscan.io/api?module=contract&action=getsourcecode&address={address}&apikey={ETHERSCAN_KEY}"
        )
        data = r.json()["result"][0]
        if not data["SourceCode"]:
            score += 15  # No audit / unverified

        # Get contract creation date
        r = requests.get(
            f"https://api.etherscan.io/api?module=account&action=txlist&address={address}&startblock=0&endblock=99999999&page=1&offset=1&sort=asc&apikey={ETHERSCAN_KEY}"
        )
        txs = r.json().get("result", [])
        if txs:
            creation_time = int(txs[0]["timeStamp"])
            days_old = (datetime.now().timestamp() - creation_time) / (3600 * 24)
            if days_old < 30:
                score += 10  # Less than a month old

    except Exception as e:
        logging.error(f"Etherscan check failed: {e}")
        score += 10  # fallback risk

    return score

# 🔍 DNS Age Check
@retry(stop_max_attempt_number=3, wait_fixed=3000)
def check_domain_age(url: str) -> int:
    try:
        domain = re.findall(r"https?://([^/]+)", url)[0]
        info = whois.whois(domain)
        created = info.creation_date
        if isinstance(created, list):
            created = created[0]
        if (datetime.now() - created).days < 30:
            return 20
        return 0
    except Exception as e:
        logging.error(f"WHOIS check failed: {e}")
        return 10  # fallback risk

# ✅ Final scam score wrapper
def analyze_airdrop(link: str, contract: str = None) -> int:
    try:
        cached = cursor.execute("SELECT score FROM scam_checks WHERE link=? AND contract=?", (link, contract)).fetchone()
        if cached:
            return cached[0]

        score = 0
        score += check_safe_browsing(link)
        score += check_domain_age(link)

        if contract:
            score += check_contract(contract)

        # Cache it
        cursor.execute("INSERT INTO scam_checks VALUES (?, ?, ?, ?)", (link, contract, score, datetime.now().isoformat()))
        conn.commit()

        return score

    except Exception as e:
        logging.error(f"Total scan failed: {e}")
        return 99  # Assume high risk on failure
