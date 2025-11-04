import os
import asyncio
import asyncssh
from typing import Tuple, List, Optional
from datetime import datetime

class BackupTransfer:
    def __init__(self):
        self.connections = {}
    
    async def connect(self, server_id: int, host: str, port: int, username: str, password: str) -> Tuple[bool, str]:
        """Подключение к резервному серверу"""
        try:
            conn = await asyncssh.connect(
                host=host,
                port=port,
                username=username,
                password=password,
                known_hosts=None
            )
            self.connections[server_id] = conn
            return True, "✅ Подключение к резервному серверу установлено"
        except asyncssh.PermissionDenied:
            return False, "❌ Ошибка аутентификации: неверный логин или пароль"
        except asyncssh.Error as e:
            return False, f"❌ Ошибка подключения: {str(e)}"
        except Exception as e:
            return False, f"❌ Неизвестная ошибка: {str(e)}"
    
    async def upload_backup(self, server_id: int, local_file_path: str, remote_path: str) -> Tuple[bool, str]:
        """Загрузка файла бэкапа на резервный сервер"""
        if server_id not in self.connections:
            return False, "❌ Соединение с резервным сервером не установлено"
        
        try:
            conn = self.connections[server_id]
            
            # Создаем удаленную директорию если не существует
            await conn.run(f"mkdir -p {remote_path}")
            
            # Получаем имя файла
            file_name = os.path.basename(local_file_path)
            remote_file_path = os.path.join(remote_path, file_name).replace('\\', '/')
            
            # Загружаем файл через SFTP
            async with conn.start_sftp_client() as sftp:
                await sftp.put(local_file_path, remote_file_path)
            
            return True, f"✅ Бэкап успешно загружен на резервный сервер: {file_name}"
            
        except Exception as e:
            return False, f"❌ Ошибка загрузки бэкапа: {str(e)}"
    
    async def list_backup_files(self, server_id: int, remote_path: str) -> Tuple[bool, List[str], str]:
        """Получение списка файлов бэкапов на резервном сервере"""
        if server_id not in self.connections:
            return False, [], "❌ Соединение с резервным сервером не установлено"
        
        try:
            conn = self.connections[server_id]
            
            # Проверяем существование директории
            result = await conn.run(f"test -d {remote_path} && echo 'EXISTS' || echo 'NOT_EXISTS'")
            if 'NOT_EXISTS' in result.stdout:
                return True, [], "📁 Директория для бэкапов не существует"
            
            # Получаем список файлов
            result = await conn.run(f"find {remote_path} -type f -name '*.sql' -o -name '*.db' -o -name '*.bson' | sort -r")
            files = [f.strip() for f in result.stdout.split('\n') if f.strip()]
            
            return True, files, f"📁 Найдено {len(files)} файлов бэкапов"
            
        except Exception as e:
            return False, [], f"❌ Ошибка получения списка файлов: {str(e)}"
    
    async def download_backup(self, server_id: int, remote_file_path: str, local_dir: str) -> Tuple[bool, str]:
        """Скачивание файла бэкапа с резервного сервера"""
        if server_id not in self.connections:
            return False, "❌ Соединение с резервным сервером не установлено"
        
        try:
            conn = self.connections[server_id]
            
            # Создаем локальную директорию если не существует
            os.makedirs(local_dir, exist_ok=True)
            
            # Получаем имя файла
            file_name = os.path.basename(remote_file_path)
            local_file_path = os.path.join(local_dir, file_name)
            
            # Скачиваем файл через SFTP
            async with conn.start_sftp_client() as sftp:
                await sftp.get(remote_file_path, local_file_path)
            
            return True, f"✅ Бэкап успешно скачан: {file_name}"
            
        except Exception as e:
            return False, f"❌ Ошибка скачивания бэкапа: {str(e)}"
    
    async def delete_backup(self, server_id: int, remote_file_path: str) -> Tuple[bool, str]:
        """Удаление файла бэкапа с резервного сервера"""
        if server_id not in self.connections:
            return False, "❌ Соединение с резервным сервером не установлено"
        
        try:
            conn = self.connections[server_id]
            
            # Удаляем файл
            result = await conn.run(f"rm -f {remote_file_path}")
            
            if result.exit_status == 0:
                return True, "✅ Файл бэкапа удален с резервного сервера"
            else:
                return False, f"❌ Ошибка удаления файла: {result.stderr}"
            
        except Exception as e:
            return False, f"❌ Ошибка удаления бэкапа: {str(e)}"
    
    async def close_connection(self, server_id: int) -> bool:
        """Закрытие соединения с резервным сервером"""
        try:
            if server_id in self.connections:
                self.connections[server_id].close()
                del self.connections[server_id]
            return True
        except:
            return False
    
    def is_connected(self, server_id: int) -> bool:
        """Проверка активного соединения"""
        return server_id in self.connections

# Глобальный экземпляр для передачи бэкапов
backup_transfer = BackupTransfer()