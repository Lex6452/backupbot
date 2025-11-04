import os
import asyncio
import subprocess
from datetime import datetime
from typing import Tuple

async def backup_postgresql(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    backup_dir: str,
    name: str
) -> Tuple[bool, str]:
    """Создание бэкапа PostgreSQL с помощью pg_dump"""
    try:
        # Формирование имени файла
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{name}_{timestamp}.sql"
        filepath = os.path.join(backup_dir, filename)
        
        # Установка переменной окружения с паролем
        env = os.environ.copy()
        env['PGPASSWORD'] = password
        
        # Команда pg_dump
        cmd = [
            'pg_dump',
            '-h', host,
            '-p', str(port),
            '-U', user,
            '-d', database,
            '-f', filepath,
            '--no-password'
        ]
        
        # Выполнение команды
        process = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return True, filepath
        else:
            error_msg = stderr.decode().strip()
            return False, f"Ошибка pg_dump: {error_msg}"
            
    except Exception as e:
        return False, f"Исключение: {str(e)}"