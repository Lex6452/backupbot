import asyncio
import logging
import logging.handlers
import os
import warnings
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Подавление предупреждений cryptography
warnings.filterwarnings("ignore", message=".*TripleDES.*")

from handlers import admin, backup, ssh_handlers
from utils.scheduler import setup_scheduler
from utils.db import init_db

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            'logs/bot.log', maxBytes=1024*1024, backupCount=5
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def main():
    """Основная функция запуска бота"""
    # Проверка обязательных переменных
    if not os.getenv('BOT_TOKEN'):
        logger.error("BOT_TOKEN не установлен в .env файле")
        return
    
    if not os.getenv('ADMIN_ID'):
        logger.error("ADMIN_ID не установлен в .env файле")
        return
    
    # Создание папки для бэкапов
    os.makedirs(os.getenv('BACKUP_DIR', './backups'), exist_ok=True)
    
    # Инициализация базы данных
    await init_db()
    
    # Инициализация бота и диспетчера
    bot = Bot(token=os.getenv('BOT_TOKEN'))
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)
    
    # Регистрация роутеров
    dp.include_router(admin.router)
    dp.include_router(backup.router)
    dp.include_router(ssh_handlers.router) 
    
    # Настройка планировщика
    await setup_scheduler(bot)
    
    logger.info("Бот запущен")
    
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        await bot.session.close()

if __name__ == '__main__':
    asyncio.run(main())