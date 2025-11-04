import asyncio
import subprocess
import platform
import re
from typing import Tuple, Optional

async def ping_server(host: str, timeout: int = 2) -> bool:
    """
    БЫСТРАЯ проверка доступности сервера через ping (1 пакет)
    """
    try:
        # Определяем параметры для разных ОС
        if platform.system().lower() == "windows":
            param = "-n"
            timeout_param = "-w"
            timeout_value = str(timeout * 1000)  # Windows в миллисекундах
        else:
            param = "-c"
            timeout_param = "-W"
            timeout_value = str(timeout)  # Linux в секундах
        
        # Выполняем ping с ОДНИМ пакетом и коротким таймаутом
        process = await asyncio.create_subprocess_exec(
            "ping", param, "1", timeout_param, timeout_value, host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Ждем завершения с таймаутом
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout + 1)
            return process.returncode == 0
        except asyncio.TimeoutError:
            # Если процесс завис, убиваем его
            try:
                process.kill()
                await process.communicate()
            except:
                pass
            return False
        
    except Exception:
        return False

async def measure_ping(host: str, count: int = 4) -> Tuple[bool, Optional[float], str]:
    """
    Детальное измерение пинга до сервера (для отдельной кнопки "Пинг")
    """
    try:
        # Определяем параметры для разных ОС
        if platform.system().lower() == "windows":
            param = "-n"
            timeout_param = "-w"
        else:
            param = "-c"
            timeout_param = "-W"
        
        # Выполняем ping с несколькими запросами для точности
        process = await asyncio.create_subprocess_exec(
            "ping", param, str(count), timeout_param, "5000", host,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        output = stdout.decode('utf-8', errors='ignore') if stdout else ""
        error_output = stderr.decode('utf-8', errors='ignore') if stderr else ""
        
        if process.returncode != 0:
            return False, None, f"❌ Сервер недоступен\n{error_output}"
        
        # Парсим результат ping для разных ОС
        if platform.system().lower() == "windows":
            return parse_windows_ping(output, host)
        else:
            return parse_linux_ping(output, host)
            
    except Exception as e:
        return False, None, f"❌ Ошибка измерения пинга: {str(e)}"

def parse_windows_ping(output: str, host: str) -> Tuple[bool, Optional[float], str]:
    """Парсинг результата ping на Windows"""
    try:
        # Ищем строку с временем пинга
        lines = output.split('\n')
        ping_times = []
        
        for line in lines:
            line = line.strip()
            # Ищем строки типа: "Время приема-передачи=32мс"
            if "мс" in line and "=" in line:
                # Разные форматы в разных локализациях
                if "Время приема-передачи" in line:  # Русская локализация
                    match = re.search(r'=(\d+)мс', line)
                elif "time=" in line:  # Английская локализация
                    match = re.search(r'time=(\d+)ms', line)
                else:
                    continue
                
                if match:
                    ping_time = int(match.group(1))
                    ping_times.append(ping_time)
        
        if ping_times:
            avg_ping = sum(ping_times) / len(ping_times)
            
            # Ищем статистику потерь пакетов
            packet_loss = "неизвестно"
            for line in lines:
                if "потерь" in line or "loss" in line:
                    packet_loss_match = re.search(r'\((\d+)%', line)
                    if packet_loss_match:
                        packet_loss = f"{packet_loss_match.group(1)}%"
                    break
            
            details = f"🏓 Результат пинга {host}:\n"
            details += f"📊 Пакеты отправлено: {len(ping_times)}\n"
            details += f"📈 Потери пакетов: {packet_loss}\n"
            details += f"⏱️ Время пинга: {min(ping_times)}-{max(ping_times)} мс\n"
            details += f"📊 Средний пинг: {avg_ping:.1f} мс"
            
            return True, avg_ping, details
        
        return False, None, "❌ Не удалось измерить пинг"
        
    except Exception as e:
        return False, None, f"❌ Ошибка парсинга пинга: {str(e)}"

def parse_linux_ping(output: str, host: str) -> Tuple[bool, Optional[float], str]:
    """Парсинг результата ping на Linux"""
    try:
        lines = output.split('\n')
        ping_times = []
        
        # Ищем строки с временем пинга
        for line in lines:
            line = line.strip()
            # Формат: "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=1.23 ms"
            if "time=" in line:
                match = re.search(r'time=([\d.]+)\s*ms', line)
                if match:
                    ping_time = float(match.group(1))
                    ping_times.append(ping_time)
        
        if ping_times:
            avg_ping = sum(ping_times) / len(ping_times)
            
            # Ищем статистику в конце вывода
            packet_loss = "0%"
            for line in lines:
                if "packet loss" in line:
                    packet_loss_match = re.search(r'(\d+)% packet loss', line)
                    if packet_loss_match:
                        packet_loss = f"{packet_loss_match.group(1)}%"
                    break
            
            # Ищем min/avg/max/mdev
            stats_line = ""
            for line in lines:
                if "min/avg/max/mdev" in line:
                    stats_line = line
                    break
            
            details = f"🏓 Результат пинга {host}:\n"
            details += f"📊 Пакеты отправлено: {len(ping_times)}\n"
            details += f"📈 Потери пакетов: {packet_loss}\n"
            details += f"⏱️ Время пинга: {min(ping_times):.1f}-{max(ping_times):.1f} мс\n"
            details += f"📊 Средний пинг: {avg_ping:.1f} мс"
            
            if stats_line:
                # Добавляем детальную статистику если есть
                stats_match = re.search(r'([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', stats_line)
                if stats_match:
                    details += f"\n📈 Детально: min={stats_match.group(1)}/avg={stats_match.group(2)}/max={stats_match.group(3)}/mdev={stats_match.group(4)} мс"
            
            return True, avg_ping, details
        
        return False, None, "❌ Не удалось измерить пинг"
        
    except Exception as e:
        return False, None, f"❌ Ошибка парсинга пинга: {str(e)}"

async def execute_ssh_command(host: str, port: int, username: str, password: str, command: str) -> Tuple[bool, str]:
    """
    Выполнение одной команды по SSH
    """
    try:
        import asyncssh
        
        async with asyncssh.connect(
            host=host,
            port=port,
            username=username,
            password=password,
            known_hosts=None,
            connect_timeout=10
        ) as conn:
            result = await conn.run(command)
            
            if result.exit_status == 0:
                return True, result.stdout or "Команда выполнена успешно"
            else:
                return False, result.stderr or f"Команда завершилась с кодом {result.exit_status}"
                
    except Exception as e:
        return False, str(e)