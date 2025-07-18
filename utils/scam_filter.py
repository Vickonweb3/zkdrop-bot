import re

# 🚫 Keywords that usually indicate scam
SCAM_KEYWORDS = [
    "free money", "double your crypto", "click here", "urgent", "giveaway", 
    "send eth", "private key", "seed phrase", "airdrop scam", "verify wallet",
    "connect wallet to claim", "uniswap clone", "1inch fake", "magic airdrop"
]

# 🔎 Basic URL pattern matching
SCAM_DOMAINS = [
    r"(?:http|https)://(?:www\.)?(scam|fake|airdrop\-claim|wallet\-connect)\.\w+"
]

# ✅ Function to check if airdrop content looks suspicious
def is_scam(content: str) -> bool:
    text = content.lower()

    for keyword in SCAM_KEYWORDS:
        if keyword in text:
            return True

    for pattern in SCAM_DOMAINS:
        if re.search(pattern, text):
            return True

    return False
