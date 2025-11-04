import asyncio
import asyncpg
import pymysql
import paramiko
from io import StringIO
import aiosqlite
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import logging

logger = logging.getLogger(__name__)

async def test_connection(connection):
    """Тестирование подключения к базе данных"""
    db_type = connection['db_type']
    
    try:
        if db_type == 'psql':
            return await test_postgresql(connection)
        elif db_type == 'mysql':
            return await test_mysql(connection)
        elif db_type == 'sqlite':
            return await test_sqlite(connection)
        elif db_type == 'mongo':
            return await test_mongodb(connection)
        else:
            return False, f"Неизвестный тип БД: {db_type}"
    except Exception as e:
        logger.error(f"Ошибка тестирования подключения: {e}")
        return False, f"Ошибка тестирования: {str(e)}"

async def test_postgresql(connection):
    """Тестирование подключения PostgreSQL"""
    try:
        conn = await asyncpg.connect(
            host=connection['host'],
            port=connection['port'],
            user=connection['user'],
            password=connection['password'],
            database=connection['database'],
            timeout=10
        )
        
        # Получаем информацию о БД
        version = await conn.fetchval('SELECT version()')
        db_size = await conn.fetchval('SELECT pg_size_pretty(pg_database_size($1))', connection['database'])
        active_connections = await conn.fetchval(
            'SELECT count(*) FROM pg_stat_activity WHERE datname = $1',
            connection['database']
        )
        
        await conn.close()
        
        message = f"PostgreSQL версия: {version.split(',')[0]}\n"
        message += f"Размер БД: {db_size}\n"
        message += f"Активных подключений: {active_connections}"
        
        return True, message
        
    except Exception as e:
        return False, f"Ошибка подключения: {str(e)}"

async def test_mysql(connection):
    """Тестирование подключения MySQL"""
    try:
        conn = pymysql.connect(
            host=connection['host'],
            port=connection['port'],
            user=connection['user'],
            password=connection['password'],
            database=connection['database'],
            connect_timeout=10
        )
        
        with conn.cursor() as cursor:
            # Получаем информацию о БД
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            
            cursor.execute("SELECT @@version_comment")
            version_comment = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT TABLE_SCHEMA as 'Database', 
                ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as 'Size_MB'
                FROM information_schema.tables 
                WHERE table_schema = %s
                GROUP BY table_schema
            """, (connection['database'],))
            db_info = cursor.fetchone()
            db_size = f"{db_info[1]} MB" if db_info else "N/A"
        
        conn.close()
        
        message = f"MySQL версия: {version}\n"
        message += f"Комментарий: {version_comment}\n"
        message += f"Размер БД: {db_size}"
        
        return True, message
        
    except Exception as e:
        return False, f"Ошибка подключения: {str(e)}"

async def test_sqlite(connection):
    """Тестирование подключения SQLite"""
    try:
        file_path = connection['file_path']
        
        # Проверяем SSH подключение если требуется
        if connection.get('ssh_host'):
            return await test_sqlite_ssh(connection)
        
        # Локальный файл
        if not file_path:
            return False, "Не указан путь к файлу"
        
        # Пытаемся подключиться к файлу
        async with aiosqlite.connect(file_path) as db:
            cursor = await db.execute("SELECT sqlite_version()")
            version = await cursor.fetchone()
            
            cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = await cursor.fetchall()
            
            cursor = await db.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            db_size = await cursor.fetchone()
            
        message = f"SQLite версия: {version[0]}\n"
        message += f"Количество таблиц: {len(tables)}\n"
        message += f"Размер БД: {db_size[0] / 1024 / 1024:.2f} MB"
        
        return True, message
        
    except Exception as e:
        return False, f"Ошибка подключения: {str(e)}"

async def test_sqlite_ssh(connection):
    """Тестирование SQLite через SSH"""
    try:
        ssh_host = connection['ssh_host']
        ssh_port = connection.get('ssh_port', 22)
        ssh_user = connection['ssh_user']
        ssh_password = connection['ssh_password']
        file_path = connection['file_path']
        
        # Создаем SSH клиент
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Подключаемся по SSH
        ssh.connect(ssh_host, port=ssh_port, username=ssh_user, password=ssh_password, timeout=10)
        
        # Проверяем существование файла
        stdin, stdout, stderr = ssh.exec_command(f"test -f {file_path} && echo 'EXISTS' || echo 'NOT_EXISTS'")
        file_exists = stdout.read().decode().strip()
        
        if file_exists != 'EXISTS':
            ssh.close()
            return False, f"Файл не найден по пути: {file_path}"
        
        # Получаем информацию о файле
        stdin, stdout, stderr = ssh.exec_command(f"stat -c '%s' {file_path}")
        file_size = stdout.read().decode().strip()
        
        # Пытаемся выполнить простой SQL запрос
        stdin, stdout, stderr = ssh.exec_command(f"sqlite3 {file_path} 'SELECT sqlite_version();'")
        version_output = stdout.read().decode().strip()
        error_output = stderr.read().decode().strip()
        
        ssh.close()
        
        if error_output and "not found" in error_output:
            return False, "SQLite3 не установлен на удаленном сервере"
        
        if version_output:
            message = f"SQLite версия: {version_output}\n"
            message += f"Размер файла: {int(file_size) / 1024 / 1024:.2f} MB\n"
            message += f"SSH подключение: ✅ Успешно"
            return True, message
        else:
            return False, "Не удалось выполнить SQL запрос через SSH"
            
    except Exception as e:
        return False, f"Ошибка SSH подключения: {str(e)}"

async def test_mongodb(connection):
    """Тестирование подключения MongoDB"""
    try:
        client = MongoClient(
            host=connection['host'],
            port=connection['port'],
            username=connection['user'],
            password=connection['password'],
            serverSelectionTimeoutMS=10000
        )
        
        # Тестируем подключение
        client.admin.command('ismaster')
        
        # Получаем информацию о БД
        db = client[connection['database']]
        db_stats = db.command('dbStats')
        
        # Получаем список коллекций
        collections = db.list_collection_names()
        
        client.close()
        
        message = f"MongoDB подключение: ✅ Успешно\n"
        message += f"Количество коллекций: {len(collections)}\n"
        message += f"Размер БД: {db_stats['dataSize'] / 1024 / 1024:.2f} MB"
        
        return True, message
        
    except ServerSelectionTimeoutError:
        return False, "Таймаут подключения к MongoDB"
    except Exception as e:
        return False, f"Ошибка подключения: {str(e)}"