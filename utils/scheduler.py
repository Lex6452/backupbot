import os
import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

from utils.db import get_enabled_connections, log_backup, get_enabled_backup_server
from utils.backup_transfer import backup_transfer
from .backup_psql import backup_postgresql
from .backup_mysql import backup_mysql
from .backup_sqlite import backup_sqlite
from .backup_mongo import backup_mongodb

logger = logging.getLogger(__name__)



async def upload_to_backup_server(local_file_path: str, backup_server: dict) -> bool:
    """Загрузка бэкапа на резервный сервер"""
    try:
        # Подключаемся к резервному серверу
        success, message = await backup_transfer.connect(
            server_id=backup_server['id'],
            host=backup_server['host'],
            port=backup_server['port'],
            username=backup_server['username'],
            password=backup_server['password']
        )
        
        if not success:
            logger.error(f"Ошибка подключения к резервному серверу: {message}")
            return False
        
        # Загружаем файл
        success, message = await backup_transfer.upload_backup(
            server_id=backup_server['id'],
            local_file_path=local_file_path,
            remote_path=backup_server['remote_path']
        )
        
        # Закрываем соединение
        await backup_transfer.close_connection(backup_server['id'])
        
        if success:
            logger.info(f"Бэкап загружен на резервный сервер: {message}")
            return True
        else:
            logger.error(f"Ошибка загрузки на резервный сервер: {message}")
            return False
            
    except Exception as e:
        logger.error(f"Неожиданная ошибка при загрузке на резервный сервер: {e}")
        return False

async def perform_auto_backup(bot):
    """Выполнение автоматического бэкапа для всех включенных подключений"""
    admin_id = int(os.getenv('ADMIN_ID'))
    backup_dir = os.getenv('BACKUP_DIR', './backups')
    
    connections = await get_enabled_connections()
    backup_server = await get_enabled_backup_server()
    
    if not connections:
        logger.info("Нет включенных подключений для автобэкапа")
        return
    
    success_count = 0
    error_count = 0
    backup_success_count = 0
    report_message = "📊 Отчет автобэкапа:\n\n"
    
    for conn in connections:
        try:
            success, result = await perform_single_backup(conn, backup_dir)
            
            await log_backup(conn['id'], success, result if not success else None)
            
            if success:
                success_count += 1
                report_message += f"✅ {conn['name']} - Успешно\n"
                logger.info(f"Автобэкап успешен: {conn['name']}")
                
                # Если есть резервный сервер, загружаем туда
                if backup_server:
                    backup_success = await upload_to_backup_server(result, backup_server)
                    if backup_success:
                        backup_success_count += 1
                        report_message += f"  📦 Загружено на резервный сервер\n"
                    else:
                        report_message += f"  ❌ Ошибка загрузки на резервный сервер\n"
                
            else:
                error_count += 1
                report_message += f"❌ {conn['name']} - Ошибка: {result}\n"
                logger.error(f"Ошибка автобэкапа {conn['name']}: {result}")
                
        except Exception as e:
            error_count += 1
            error_msg = f"Неожиданная ошибка: {str(e)}"
            await log_backup(conn['id'], False, error_msg)
            report_message += f"❌ {conn['name']} - Ошибка: {error_msg}\n"
            logger.error(f"Неожиданная ошибка автобэкапа {conn['name']}: {e}")
    
    if backup_server and success_count > 0:
        report_message += f"\n📦 Резервное копирование: {backup_success_count}/{success_count} успешно"
    
    report_message += f"\n\nИтого: ✅ {success_count} | ❌ {error_count}"
    
    # Отправка отчета админу
    try:
        await bot.send_message(admin_id, report_message)
    except Exception as e:
        logger.error(f"Ошибка отправки отчета админу: {e}")

async def perform_single_backup(conn, backup_dir):
    """Выполнение бэкапа для одного подключения"""
    db_type = conn['db_type']
    
    if db_type == 'psql':
        return await backup_postgresql(
            conn['host'], conn['port'], conn['database'],
            conn['user'], conn['password'], backup_dir, conn['name']
        )
    elif db_type == 'mysql':
        return await backup_mysql(
            conn['host'], conn['port'], conn['database'],
            conn['user'], conn['password'], backup_dir, conn['name']
        )
    elif db_type == 'sqlite':
        # Для SQLite передаем SSH параметры если они есть
        return await backup_sqlite(
            conn['file_path'], backup_dir, conn['name'],
            conn.get('ssh_host'), conn.get('ssh_port', 22),
            conn.get('ssh_user'), conn.get('ssh_password')
        )
    elif db_type == 'mongo':
        return await backup_mongodb(
            conn['host'], conn['port'], conn['database'],
            conn['user'], conn['password'], backup_dir, conn['name']
        )
    else:
        return False, f"Неизвестный тип БД: {db_type}"

async def setup_scheduler(bot):
    """Настройка планировщика для автоматических бэкапов"""
    scheduler = AsyncIOScheduler()
    
    # Запуск ежедневно в 02:00
    scheduler.add_job(
        perform_auto_backup,
        trigger=CronTrigger(hour=2, minute=0),
        args=[bot],
        id='auto_backup'
    )
    
    scheduler.start()
    logger.info("Планировщик автобэкапов запущен (ежедневно в 02:00)")

async def perform_single_backup_with_retry(conn, backup_dir, max_retries=2):
    for attempt in range(max_retries):
        success, result = await perform_single_backup(conn, backup_dir)
        if success:
            return success, result
        elif attempt < max_retries - 1:
            await asyncio.sleep(5)  # пауза перед повторной попыткой
    return success, result