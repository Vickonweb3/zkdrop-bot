from aiogram import Bot, Dispatcher, executor, types
from config.settings import BOT_TOKEN
from handlers import start_handler, airdrop_notify, admin_handler, menu_handler
from utils.scheduler import start_scheduler
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

# Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Register handlers
start_handler.register_start(dp)
airdrop_notify.register_notify(dp)
admin_handler.register_admin(dp)
menu_handler.register_menu(dp)

# Start scheduled background tasks
start_scheduler(bot)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
