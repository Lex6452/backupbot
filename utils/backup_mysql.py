import os
import asyncio
import subprocess
from datetime import datetime
from typing import Tuple

async def backup_mysql(
    host: str,
    port: int,
    database: str,
    user: str,
    password: str,
    backup_dir: str,
    name: str
) -> Tuple[bool, str]:
    """Создание бэкапа MySQL с помощью mysqldump"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{name}_{timestamp}.sql"
        filepath = os.path.join(backup_dir, filename)
        
        # Команда mysqldump
        cmd = [
            'mysqldump',
            f'-h{host}',
            f'-P{port}',
            f'-u{user}',
            f'-p{password}',
            '--single-transaction',
            '--quick',
            database
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            # Сохранение результата в файл
            with open(filepath, 'wb') as f:
                f.write(stdout)
            return True, filepath
        else:
            error_msg = stderr.decode().strip()
            return False, f"Ошибка mysqldump: {error_msg}"
            
    except Exception as e:
        return False, f"Исключение: {str(e)}"