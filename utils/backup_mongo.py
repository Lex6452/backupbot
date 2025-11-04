import os
import asyncio
import subprocess
from datetime import datetime
from typing import Tuple

async def backup_mongodb(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    backup_dir: str,
    name: str
) -> Tuple[bool, str]:
    """Создание бэкапа MongoDB с помощью mongodump"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        dirname = f"{name}_{timestamp}"
        dirpath = os.path.join(backup_dir, dirname)
        
        # Базовая команда mongodump
        cmd = [
            'mongodump',
            f'--host={host}:{port}',
            f'--db={database}',
            f'--out={dirpath}'
        ]
        
        # Добавление аутентификации если есть
        if user and password:
            cmd.extend([
                f'--username={user}',
                f'--password={password}',
                '--authenticationDatabase=admin'
            ])
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            return True, dirpath
        else:
            error_msg = stderr.decode().strip()
            return False, f"Ошибка mongodump: {error_msg}"
            
    except Exception as e:
        return False, f"Исключение: {str(e)}"