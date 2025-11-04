import os
import shutil
import aiofiles
import paramiko
from io import BytesIO
from datetime import datetime
from typing import Tuple

async def backup_sqlite(
    file_path: str,
    backup_dir: str,
    name: str,
    ssh_host: str = None,
    ssh_port: int = 22,
    ssh_user: str = None,
    ssh_password: str = None
) -> Tuple[bool, str]:
    """Создание бэкапа SQLite"""
    try:
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{name}_{timestamp}.db"
        filepath = os.path.join(backup_dir, filename)
        
        if ssh_host:
            # Бэкап через SSH
            return await backup_sqlite_ssh(
                ssh_host, ssh_port, ssh_user, ssh_password,
                file_path, filepath, name
            )
        else:
            # Локальный бэкап
            return await backup_sqlite_local(file_path, filepath, name)
        
    except Exception as e:
        return False, f"Исключение: {str(e)}"

async def backup_sqlite_local(file_path: str, backup_path: str, name: str) -> Tuple[bool, str]:
    """Локальный бэкап SQLite"""
    try:
        if not os.path.exists(file_path):
            return False, f"Файл не найден: {file_path}"
        
        # Копирование файла
        async with aiofiles.open(file_path, 'rb') as source_file:
            async with aiofiles.open(backup_path, 'wb') as backup_file:
                content = await source_file.read()
                await backup_file.write(content)
        
        return True, backup_path
        
    except Exception as e:
        return False, f"Ошибка локального бэкапа: {str(e)}"

async def backup_sqlite_ssh(
    ssh_host: str,
    ssh_port: int,
    ssh_user: str,
    ssh_password: str,
    remote_path: str,
    local_path: str,
    name: str
) -> Tuple[bool, str]:
    """Бэкап SQLite через SSH"""
    try:
        # Создаем SSH клиент
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Подключаемся по SSH
        ssh.connect(ssh_host, port=ssh_port, username=ssh_user, password=ssh_password, timeout=30)
        
        # Проверяем существование файла
        stdin, stdout, stderr = ssh.exec_command(f"test -f {remote_path} && echo 'EXISTS' || echo 'NOT_EXISTS'")
        file_exists = stdout.read().decode().strip()
        
        if file_exists != 'EXISTS':
            ssh.close()
            return False, f"Файл не найден на сервере по пути: {remote_path}"
        
        # Создаем SFTP сессию
        sftp = ssh.open_sftp()
        
        # Скачиваем файл
        sftp.get(remote_path, local_path)
        
        # Закрываем соединения
        sftp.close()
        ssh.close()
        
        return True, local_path
        
    except Exception as e:
        return False, f"Ошибка SSH бэкапа: {str(e)}"