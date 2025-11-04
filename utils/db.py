import aiosqlite
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

DB_PATH = 'connections.db'

async def init_db():
    """Инициализация базы данных для хранения подключений"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Основная таблица подключений
        await db.execute('''
            CREATE TABLE IF NOT EXISTS connections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                db_type TEXT NOT NULL CHECK(db_type IN ('psql', 'mysql', 'sqlite', 'mongo')),
                host TEXT,
                port INTEGER,
                database TEXT,
                user TEXT,
                password TEXT,
                file_path TEXT,
                ssh_host TEXT,
                ssh_port INTEGER DEFAULT 22,
                ssh_user TEXT,
                ssh_password TEXT,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица логов бэкапов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS backup_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id INTEGER,
                success BOOLEAN,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (connection_id) REFERENCES connections (id)
            )
        ''')
        
        # Таблица SSH серверов
        await db.execute('''
            CREATE TABLE IF NOT EXISTS ssh_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER DEFAULT 22,
                username TEXT NOT NULL,
                password TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица логов SSH сессий
        await db.execute('''
            CREATE TABLE IF NOT EXISTS ssh_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id INTEGER,
                command TEXT,
                output TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (server_id) REFERENCES ssh_servers (id)
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS backup_servers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                host TEXT NOT NULL,
                port INTEGER DEFAULT 22,
                username TEXT NOT NULL,
                password TEXT,
                remote_path TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await db.execute('CREATE INDEX IF NOT EXISTS idx_connections_enabled ON connections(enabled)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_backup_logs_created ON backup_logs(created_at)')
        await db.execute('CREATE INDEX IF NOT EXISTS idx_ssh_servers_host ON ssh_servers(host)')
        
        await db.commit()

async def add_connection(
    name: str,
    db_type: str,
    host: str = None,
    port: int = None,
    database: str = None,
    user: str = None,
    password: str = None,
    file_path: str = None,
    ssh_host: str = None,
    ssh_port: int = 22,
    ssh_user: str = None,
    ssh_password: str = None,
    enabled: bool = True
) -> int:
    """Добавление нового подключения к БД"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO connections 
            (name, db_type, host, port, database, user, password, file_path, 
             ssh_host, ssh_port, ssh_user, ssh_password, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name, db_type, host, port, database, user, password, file_path,
            ssh_host, ssh_port, ssh_user, ssh_password, enabled
        ))
        await db.commit()
        return cursor.lastrowid

async def get_connections() -> List[Dict[str, Any]]:
    """Получение списка всех подключений"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM connections ORDER BY created_at DESC')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_connection(connection_id: int) -> Optional[Dict[str, Any]]:
    """Получение подключения по ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM connections WHERE id = ?', (connection_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_enabled_connections() -> List[Dict[str, Any]]:
    """Получение списка включенных подключений"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM connections WHERE enabled = 1')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def update_connection_enabled(connection_id: int, enabled: bool) -> bool:
    """Обновление статуса подключения"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            'UPDATE connections SET enabled = ? WHERE id = ?',
            (enabled, connection_id)
        )
        await db.commit()
        return cursor.rowcount > 0

async def update_connection(connection_id: int, updates: Dict[str, Any]) -> bool:
    """Обновление данных подключения"""
    if not updates:
        return False
    
    # Формируем SET часть запроса
    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values())
    values.append(connection_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f'UPDATE connections SET {set_clause} WHERE id = ?',
            values
        )
        await db.commit()
        return cursor.rowcount > 0

async def delete_connection(connection_id: int) -> bool:
    """Удаление подключения"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM connections WHERE id = ?', (connection_id,))
        await db.commit()
        return cursor.rowcount > 0

async def log_backup(connection_id: int, success: bool, error_message: str = None):
    """Логирование результата бэкапа"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO backup_logs (connection_id, success, error_message) VALUES (?, ?, ?)',
            (connection_id, success, error_message)
        )
        await db.commit()

async def get_recent_logs(limit: int = 10) -> List[Dict[str, Any]]:
    """Получение последних логов бэкапов"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT bl.*, c.name as connection_name 
            FROM backup_logs bl 
            LEFT JOIN connections c ON bl.connection_id = c.id 
            ORDER BY bl.created_at DESC 
            LIMIT ?
        ''', (limit,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    
async def add_ssh_server(
    name: str,
    host: str,
    port: int = 22,
    username: str = "root",
    password: str = None
) -> int:
    """Добавление нового SSH сервера"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO ssh_servers (name, host, port, username, password)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, host, port, username, password))
        await db.commit()
        return cursor.lastrowid

async def get_ssh_servers() -> List[Dict[str, Any]]:
    """Получение списка всех SSH серверов"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM ssh_servers ORDER BY created_at DESC')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_ssh_server(server_id: int) -> Optional[Dict[str, Any]]:
    """Получение SSH сервера по ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM ssh_servers WHERE id = ?', (server_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_ssh_server(server_id: int, updates: Dict[str, Any]) -> bool:
    """Обновление данных SSH сервера"""
    if not updates:
        return False
    
    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values())
    values.append(server_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f'UPDATE ssh_servers SET {set_clause} WHERE id = ?',
            values
        )
        await db.commit()
        return cursor.rowcount > 0

async def delete_ssh_server(server_id: int) -> bool:
    """Удаление SSH сервера"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM ssh_servers WHERE id = ?', (server_id,))
        await db.commit()
        return cursor.rowcount > 0

async def log_ssh_command(server_id: int, command: str, output: str):
    """Логирование SSH команды"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'INSERT INTO ssh_logs (server_id, command, output) VALUES (?, ?, ?)',
            (server_id, command, output)
        )
        await db.commit()

async def get_ssh_logs(server_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Получение логов SSH сессий"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('''
            SELECT * FROM ssh_logs 
            WHERE server_id = ? 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (server_id, limit))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def add_backup_server(
    name: str,
    host: str,
    port: int = 22,
    username: str = "root",
    password: str = None,
    remote_path: str = "/backups",
    enabled: bool = True
) -> int:
    """Добавление нового резервного сервера"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('''
            INSERT INTO backup_servers (name, host, port, username, password, remote_path, enabled)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, host, port, username, password, remote_path, enabled))
        await db.commit()
        return cursor.lastrowid

async def get_backup_servers() -> List[Dict[str, Any]]:
    """Получение списка всех резервных серверов"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM backup_servers ORDER BY created_at DESC')
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_backup_server(server_id: int) -> Optional[Dict[str, Any]]:
    """Получение резервного сервера по ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM backup_servers WHERE id = ?', (server_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_enabled_backup_server() -> Optional[Dict[str, Any]]:
    """Получение включенного резервного сервера"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute('SELECT * FROM backup_servers WHERE enabled = 1 LIMIT 1')
        row = await cursor.fetchone()
        return dict(row) if row else None

async def update_backup_server(server_id: int, updates: Dict[str, Any]) -> bool:
    """Обновление данных резервного сервера"""
    if not updates:
        return False
    
    set_clause = ", ".join([f"{key} = ?" for key in updates.keys()])
    values = list(updates.values())
    values.append(server_id)
    
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            f'UPDATE backup_servers SET {set_clause} WHERE id = ?',
            values
        )
        await db.commit()
        return cursor.rowcount > 0

async def delete_backup_server(server_id: int) -> bool:
    """Удаление резервного сервера"""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute('DELETE FROM backup_servers WHERE id = ?', (server_id,))
        await db.commit()
        return cursor.rowcount > 0