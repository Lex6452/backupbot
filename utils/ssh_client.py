import asyncio
import asyncssh
from typing import Tuple, Optional
import os

class SSHClient:
    def __init__(self):
        self.connections = {}
        self.current_dirs = {}
    
    async def connect(self, server_id: int, host: str, port: int, username: str, password: str) -> Tuple[bool, str]:
        """Подключение к SSH серверу"""
        try:
            conn = await asyncssh.connect(
                host=host,
                port=port,
                username=username,
                password=password,
                known_hosts=None
            )
            self.connections[server_id] = conn
            
            # Получаем начальную директорию
            result = await conn.run("pwd")
            if result.exit_status == 0:
                initial_dir = result.stdout.strip()
                self.current_dirs[server_id] = initial_dir
            else:
                self.current_dirs[server_id] = "~"
            
            return True, "✅ Подключение успешно установлено"
        except asyncssh.PermissionDenied:
            return False, "❌ Ошибка аутентификации: неверный логин или пароль"
        except asyncssh.ConnectionLost:
            return False, "❌ Соединение разорвано"
        except asyncssh.Error as e:
            return False, f"❌ Ошибка подключения: {str(e)}"
        except Exception as e:
            return False, f"❌ Неизвестная ошибка: {str(e)}"
    
    async def execute_command(self, server_id: int, command: str) -> Tuple[bool, str, str]:
        """Выполнение команды на SSH сервере"""
        if server_id not in self.connections:
            return False, "", "❌ SSH соединение не установлено"
        
        try:
            conn = self.connections[server_id]
            current_dir = self.current_dirs.get(server_id, "~")
            
            # Если команда - смена директории
            if command.strip().startswith('cd '):
                # Извлекаем путь из команды cd
                path = command.strip()[3:].strip()
                if path:
                    # Обновляем текущую директорию
                    if path.startswith('/'):
                        # Абсолютный путь
                        new_dir = path
                    else:
                        # Относительный путь
                        if current_dir == "~":
                            # Если текущая директория неизвестна, используем домашнюю
                            result = await conn.run("echo $HOME")
                            home_dir = result.stdout.strip() if result.exit_status == 0 else "/root"
                            new_dir = os.path.join(home_dir, path)
                        else:
                            new_dir = os.path.join(current_dir, path)
                    
                    # Нормализуем путь
                    new_dir = os.path.normpath(new_dir)
                    self.current_dirs[server_id] = new_dir
                    
                    return True, new_dir, f"Директория изменена на: {new_dir}"
                else:
                    return False, current_dir, "❌ Не указан путь для cd"
            
            # Для обычных команд используем текущую директорию
            # Выполняем команду в текущей директории
            if current_dir != "~":
                # Если известна текущая директория, добавляем cd перед командой
                full_command = f"cd {current_dir} && {command}"
                result = await conn.run(full_command)
            else:
                result = await conn.run(command)
            
            if result.exit_status == 0:
                output = result.stdout.strip() if result.stdout else ""
                stderr = result.stderr.strip() if result.stderr else ""
                full_output = f"{output}\n{stderr}".strip()
                return True, current_dir, full_output
            else:
                error_msg = result.stderr.strip() if result.stderr else "Команда завершилась с ошибкой"
                return False, current_dir, f"❌ {error_msg}"
                
        except asyncssh.Error as e:
            return False, "", f"❌ Ошибка выполнения команды: {str(e)}"
        except Exception as e:
            return False, "", f"❌ Неизвестная ошибка: {str(e)}"
    
    async def close_connection(self, server_id: int) -> bool:
        """Закрытие SSH соединения"""
        try:
            if server_id in self.connections:
                self.connections[server_id].close()
                del self.connections[server_id]
            
            if server_id in self.current_dirs:
                del self.current_dirs[server_id]
            
            return True
        except:
            return False
    
    async def execute_command_with_timeout(self, server_id: int, command: str, timeout: int = 30) -> Tuple[bool, str, str]:
        """Выполнение команды с таймаутом"""
        if server_id not in self.connections:
            return False, "", "❌ SSH соединение не установлено"
        
        try:
            conn = self.connections[server_id]
            current_dir = self.current_dirs.get(server_id, "~")
            
            # Выполняем команду с таймаутом
            if current_dir != "~":
                full_command = f"cd {current_dir} && {command}"
            else:
                full_command = command
                
            result = await asyncio.wait_for(conn.run(full_command), timeout=timeout)
            
            if result.exit_status == 0:
                output = result.stdout.strip() if result.stdout else ""
                stderr = result.stderr.strip() if result.stderr else ""
                full_output = f"{output}\n{stderr}".strip()
                return True, current_dir, full_output
            else:
                error_msg = result.stderr.strip() if result.stderr else "Команда завершилась с ошибкой"
                return False, current_dir, f"❌ {error_msg}"
                
        except asyncio.TimeoutError:
            return False, "", "❌ Таймаут выполнения команды"
        except asyncssh.Error as e:
            return False, "", f"❌ Ошибка выполнения команды: {str(e)}"
        except Exception as e:
            return False, "", f"❌ Неизвестная ошибка: {str(e)}"
    
    def is_connected(self, server_id: int) -> bool:
        """Проверка активного соединения"""
        return server_id in self.connections
    
    def get_current_dir(self, server_id: int) -> str:
        """Получение текущей директории"""
        return self.current_dirs.get(server_id, "~")

# Глобальный экземпляр SSH клиента
ssh_client = SSHClient()