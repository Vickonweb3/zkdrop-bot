import os
from telegram import Update
from telegram.ext import ContextTypes
from scraper import scrape_zealy_airdrops

ADMIN_ID = int(os.getenv("ADMIN_ID"))

async def snipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("⛔ You're not allowed to use this.")

    drops = scrape_zealy_airdrops()
    if not drops:
        return await update.message.reply_text("⚠️ No new airdrops found.")

    for drop in drops:
        text = f"🚀 *{drop['title']}*\n📄 {drop['description']}\n🔗 [Join Now]({drop['link']})\n⭐ Score: {drop.get('score', 0)}/100"
        await update.message.reply_markdown(text, disable_web_page_preview=True)
