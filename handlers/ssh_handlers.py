import os
import asyncio
import subprocess
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from utils.db import (
    add_ssh_server, get_ssh_servers, get_ssh_server,
    update_ssh_server, delete_ssh_server, log_ssh_command
)
from utils.ssh_client import ssh_client
from utils.ssh_utils import ping_server, execute_ssh_command, measure_ping

router = Router()

# Проверка прав администратора
def is_admin(user_id: int) -> bool:
    admin_id = os.getenv('ADMIN_ID')
    if not admin_id:
        return False
    return user_id == int(admin_id)

# Классы состояний для FSM
class AddSSHServer(StatesGroup):
    entering_name = State()
    entering_host = State()
    entering_port = State()
    entering_username = State()
    entering_password = State()
    confirmation = State()

class EditSSHServer(StatesGroup):
    choosing_field = State()
    editing_field = State()

class SSHCommand(StatesGroup):
    waiting_command = State()

server_status_cache = {}
CACHE_TIMEOUT = 30

async def get_server_status(server_id: int, host: str) -> tuple:
    """Получение статуса сервера с кэшированием"""
    current_time = asyncio.get_event_loop().time()
    
    # Проверяем кэш
    if server_id in server_status_cache:
        status, timestamp = server_status_cache[server_id]
        if current_time - timestamp < CACHE_TIMEOUT:
            return status
    
    # Быстрая проверка доступности (1 пакет, короткий таймаут)
    is_online = await ping_server(host, timeout=2)
    
    # Сохраняем в кэш
    server_status_cache[server_id] = (is_online, current_time)
    
    return is_online

# Главное меню SSH
@router.callback_query(F.data == "menu_ssh")
async def menu_ssh(callback_query: CallbackQuery, state: FSMContext):
    """Главное меню SSH"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ У вас нет доступа")
        return
    
    # Показываем сообщение сразу
    await callback_query.message.edit_text("🔐 Загружаю SSH менеджер...")
    
    servers = await get_ssh_servers()
    
    text = "🔐 SSH Менеджер\n\nВыберите действие:"
    
    keyboard = InlineKeyboardBuilder()
    
    if servers:
        # Создаем задачи для параллельной проверки статусов
        status_tasks = []
        for server in servers:
            task = get_server_status(server['id'], server['host'])
            status_tasks.append(task)
        
        # Ждем завершения всех проверок
        ping_results = await asyncio.gather(*status_tasks)
        
        for i, server in enumerate(servers):
            # Статус подключения
            ssh_status = "🟢" if ssh_client.is_connected(server['id']) else "⚪"
            # Статус пинга из кэша
            ping_status = "🟢" if ping_results[i] else "🔴"
            
            keyboard.button(
                text=f"{ssh_status}{ping_status} {server['name']}", 
                callback_data=f"ssh_server_{server['id']}"
            )
    
    keyboard.button(text="➕ Добавить SSH сервер", callback_data="ssh_add_server")
    keyboard.button(text="📋 Список серверов", callback_data="ssh_list_servers")
    keyboard.button(text="🔄 Обновить", callback_data="menu_ssh")
    keyboard.button(text="🔙 Назад", callback_data="menu_main")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Добавление SSH сервера (упрощенная версия)
@router.callback_query(F.data == "ssh_add_server")
async def ssh_add_server(callback_query: CallbackQuery, state: FSMContext):
    """Начало добавления SSH сервера"""
    await state.update_data(bot_message_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        "➕ Добавление SSH сервера\n\nВведите название сервера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_ssh")
        ]])
    )
    await state.set_state(AddSSHServer.entering_name)

@router.message(AddSSHServer.entering_name)
async def process_ssh_name(message: Message, state: FSMContext):
    """Обработка названия SSH сервера"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(name=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление SSH сервера\n\n✅ Название: {message.text}\n\nВведите host (IP или домен):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="ssh_add_server")
        ]])
    )
    await state.set_state(AddSSHServer.entering_host)

@router.message(AddSSHServer.entering_host)
async def process_ssh_host(message: Message, state: FSMContext):
    """Обработка host SSH сервера"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(host=message.text)
    data = await state.get_data()
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление SSH сервера\n\n✅ Название: {data['name']}\n✅ Host: {message.text}\n\nВведите порт (по умолчанию 22):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="ssh_add_server")
        ]])
    )
    await state.set_state(AddSSHServer.entering_port)

@router.message(AddSSHServer.entering_port)
async def process_ssh_port(message: Message, state: FSMContext):
    """Обработка порта SSH сервера"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    try:
        port = int(message.text) if message.text else 22
        await state.update_data(port=port)
        data = await state.get_data()
        
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_message_id,
            text=f"➕ Добавление SSH сервера\n\n✅ Название: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {port}\n\nВведите имя пользователя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="ssh_add_server")
            ]])
        )
        await state.set_state(AddSSHServer.entering_username)
    except ValueError:
        await message.answer("❌ Порт должен быть числом. Попробуйте еще раз:")

@router.message(AddSSHServer.entering_username)
async def process_ssh_username(message: Message, state: FSMContext):
    """Обработка имени пользователя SSH сервера"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(username=message.text)
    data = await state.get_data()
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление SSH сервера\n\n✅ Название: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ Пользователь: {message.text}\n\nВведите пароль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="ssh_add_server")
        ]])
    )
    await state.set_state(AddSSHServer.entering_password)

@router.message(AddSSHServer.entering_password)
async def process_ssh_password(message: Message, state: FSMContext):
    """Обработка пароля SSH сервера"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(password=message.text)
    data = await state.get_data()
    
    text = "📋 Проверьте данные SSH сервера:\n\n"
    text += f"Название: {data['name']}\n"
    text += f"Host: {data['host']}\n"
    text += f"Порт: {data['port']}\n"
    text += f"Пользователь: {data['username']}\n"
    text += f"Пароль: {'*' * len(data['password'])}\n\n"
    text += "Сохранить сервер?"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Сохранить", callback_data="ssh_confirm_save")
    keyboard.button(text="🔗 Проверить подключение", callback_data="ssh_test_connection")
    keyboard.button(text="✏️ Редактировать", callback_data="ssh_edit_before_save")
    keyboard.button(text="🔙 Назад", callback_data="ssh_add_server")
    keyboard.adjust(1)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=text,
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(AddSSHServer.confirmation)

@router.callback_query(AddSSHServer.confirmation, F.data == "ssh_test_connection")
async def ssh_test_connection(callback_query: CallbackQuery, state: FSMContext):
    """Тестирование SSH подключения"""
    data = await state.get_data()
    
    await callback_query.message.edit_text("🔍 Проверяю SSH подключение...")
    
    success, message = await ssh_client.connect(
        server_id=0,  # временный ID для теста
        host=data['host'],
        port=data['port'],
        username=data['username'],
        password=data['password']
    )
    
    # Закрываем тестовое соединение
    if success:
        await ssh_client.close_connection(0)
    
    text = f"{message}\n\nСохранить сервер?"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Сохранить", callback_data="ssh_confirm_save")
    keyboard.button(text="✏️ Редактировать", callback_data="ssh_edit_before_save")
    keyboard.button(text="🔙 Назад", callback_data="ssh_back_to_confirmation")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(AddSSHServer.confirmation, F.data == "ssh_back_to_confirmation")
async def ssh_back_to_confirmation(callback_query: CallbackQuery, state: FSMContext):
    """Возврат к подтверждению"""
    data = await state.get_data()
    
    text = "📋 Проверьте данные SSH сервера:\n\n"
    text += f"Название: {data['name']}\n"
    text += f"Host: {data['host']}\n"
    text += f"Порт: {data['port']}\n"
    text += f"Пользователь: {data['username']}\n"
    text += f"Пароль: {'*' * len(data['password'])}\n\n"
    text += "Сохранить сервер?"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Сохранить", callback_data="ssh_confirm_save")
    keyboard.button(text="🔗 Проверить подключение", callback_data="ssh_test_connection")
    keyboard.button(text="✏️ Редактировать", callback_data="ssh_edit_before_save")
    keyboard.button(text="🔙 Назад", callback_data="ssh_add_server")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(AddSSHServer.confirmation, F.data == "ssh_edit_before_save")
async def ssh_edit_before_save(callback_query: CallbackQuery, state: FSMContext):
    """Редактирование перед сохранением"""
    data = await state.get_data()
    await state.update_data(bot_message_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        f"➕ Добавление SSH сервера\n\nТекущее название: {data['name']}\n\nВведите новое название сервера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="ssh_back_to_confirmation")
        ]])
    )
    await state.set_state(AddSSHServer.entering_name)

@router.callback_query(AddSSHServer.confirmation, F.data == "ssh_confirm_save")
async def ssh_confirm_save(callback_query: CallbackQuery, state: FSMContext):
    """Сохранение SSH сервера"""
    data = await state.get_data()
    
    try:
        server_id = await add_ssh_server(
            name=data['name'],
            host=data['host'],
            port=data['port'],
            username=data['username'],
            password=data['password']
        )
        
        await callback_query.message.edit_text(
            f"✅ SSH сервер '{data['name']}' успешно добавлен (ID: {server_id})",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔐 SSH Менеджер", callback_data="menu_ssh"),
                InlineKeyboardButton(text="➕ Добавить еще", callback_data="ssh_add_server")
            ], [
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_main")
            ]])
        )
        
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ Ошибка при добавлении SSH сервера: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="ssh_back_to_confirmation")
            ]])
        )
    
    await state.clear()

# Детальная информация о сервере
@router.callback_query(F.data.startswith("ssh_server_"))
async def ssh_server_detail(callback_query: CallbackQuery, state: FSMContext):
    """Детальная информация о SSH сервере"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    # Проверяем пинг
    is_online = await ping_server(server['host'])
    ping_status = "🟢 Онлайн" if is_online else "🔴 Офлайн"
    
    # Проверяем SSH подключение
    ssh_connected = ssh_client.is_connected(server_id)
    ssh_status = "🟢 Подключен" if ssh_connected else "⚪ Не подключен"
    
    text = f"🔐 SSH Сервер: {server['name']}\n\n"
    text += f"📍 Host: {server['host']}\n"
    text += f"🔢 Port: {server['port']}\n"
    text += f"👤 User: {server['username']}\n"
    text += f"📊 Статус: {ping_status} | {ssh_status}\n\n"
    text += "Выберите действие:"
    
    keyboard = InlineKeyboardBuilder()
    
    # Основные действия
    keyboard.button(text="🔌 Подключиться", callback_data=f"ssh_connect_{server_id}")
    keyboard.button(text="🔄 Перезагрузить", callback_data=f"ssh_reboot_{server_id}")
    keyboard.button(text="📦 Обновить библиотеки", callback_data=f"ssh_update_{server_id}")
    keyboard.button(text="🏓 Пинг", callback_data=f"ssh_ping_{server_id}")
    
    # Управление сервером
    keyboard.button(text="✏️ Редактировать", callback_data=f"ssh_edit_start_{server_id}")
    keyboard.button(text="🗑️ Удалить", callback_data=f"ssh_delete_{server_id}")
    
    keyboard.button(text="🔙 Назад", callback_data="menu_ssh")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Подключение к SSH серверу
@router.callback_query(F.data.startswith("ssh_connect_"))
async def ssh_connect(callback_query: CallbackQuery, state: FSMContext):
    """Подключение к SSH серверу"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    # Проверяем, не подключены ли уже
    if ssh_client.is_connected(server_id):
        await start_ssh_session(callback_query, state, server_id, server)
        return
    
    await callback_query.message.edit_text(f"🔗 Подключаюсь к {server['name']}...")
    
    success, message = await ssh_client.connect(
        server_id=server_id,
        host=server['host'],
        port=server['port'],
        username=server['username'],
        password=server['password']
    )
    
    if success:
        await start_ssh_session(callback_query, state, server_id, server)
    else:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="🔄 Повторить", callback_data=f"ssh_connect_{server_id}")
        keyboard.button(text="🔙 Назад", callback_data=f"ssh_server_{server_id}")
        keyboard.adjust(1)
        
        await callback_query.message.edit_text(
            f"❌ Не удалось подключиться к {server['name']}:\n{message}",
            reply_markup=keyboard.as_markup()
        )

async def start_ssh_session(callback_query: CallbackQuery, state: FSMContext, server_id: int, server: dict):
    """Начало SSH сессии"""
    current_dir = ssh_client.get_current_dir(server_id)
    
    await callback_query.message.edit_text(
        f"🔐 SSH сессия: {server['name']}\n\n"
        f"💻 {server['username']}@{server['host']}\n"
        f"📁 Текущая директория: {current_dir}\n\n"
        f"Введите команду:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Закрыть сессию", callback_data=f"ssh_close_{server_id}")
        ]])
    )
    
    # Сохраняем состояние для ожидания команд
    await state.set_state(SSHCommand.waiting_command)
    await state.update_data(server_id=server_id, server_name=server['name'], host=server['host'], username=server['username'])

@router.message(SSHCommand.waiting_command)
async def process_ssh_command(message: Message, state: FSMContext):
    """Обработка SSH команды"""
    data = await state.get_data()
    server_id = data['server_id']
    server_name = data['server_name']
    host = data['host']
    username = data['username']
    
    command = message.text.strip()
    
    if command.lower() in ['exit', 'quit']:
        await ssh_close_session(message, server_id, state)
        return
    
    # Удаляем сообщение с командой
    try:
        await message.delete()
    except:
        pass
    
    # Выполняем команду
    success, current_dir, output = await ssh_client.execute_command(server_id, command)
    
    # Логируем команду
    await log_ssh_command(server_id, command, output)
    
    if not success:
        output = f"❌ Ошибка: {output}"
    
    # Форматируем вывод
    if output:
        formatted_output = f"```\n{username}@{host}:{current_dir}# {command}\n{output}\n```"
    else:
        formatted_output = f"```\n{username}@{host}:{current_dir}# {command}\n```"
    
    # Разбиваем длинные сообщения
    if len(formatted_output) > 4000:
        chunks = [formatted_output[i:i+4000] for i in range(0, len(formatted_output), 4000)]
        for chunk in chunks:
            await message.answer(
                chunk,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="❌ Закрыть сессию", callback_data=f"ssh_close_{server_id}")
                ]])
            )
    else:
        await message.answer(
            formatted_output,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="❌ Закрыть сессию", callback_data=f"ssh_close_{server_id}")
            ]])
        )

# Перезагрузка сервера
@router.callback_query(F.data.startswith("ssh_reboot_"))
async def ssh_reboot(callback_query: CallbackQuery):
    """Перезагрузка SSH сервера"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    await callback_query.message.edit_text(f"🔄 Отправляю команду перезагрузки на {server['name']}...")
    
    # Подключаемся если не подключены
    if not ssh_client.is_connected(server_id):
        success, message = await ssh_client.connect(
            server_id=server_id,
            host=server['host'],
            port=server['port'],
            username=server['username'],
            password=server['password']
        )
        if not success:
            await callback_query.message.edit_text(f"❌ Не удалось подключиться: {message}")
            return
    
    # Отправляем команду reboot
    success, current_dir, output = await ssh_client.execute_command(server_id, "sudo reboot")
    
    if success:
        await callback_query.message.edit_text(
            f"✅ Команда перезагрузки отправлена на {server['name']}\n"
            f"Начинаю мониторинг перезагрузки..."
        )
        
        # Закрываем соединение
        await ssh_client.close_connection(server_id)
        
        # Мониторим перезагрузку
        await monitor_reboot(callback_query.message, server)
    else:
        await callback_query.message.edit_text(
            f"❌ Ошибка при отправке команды перезагрузки:\n{output}"
        )

async def monitor_reboot(message: Message, server: dict):
    """Мониторинг перезагрузки сервера"""
    import time
    start_time = time.time()
    
    # Ждем пока сервер станет недоступным
    await message.edit_text("⏳ Ожидаю отключения сервера...")
    
    max_wait_time = 300  # 5 минут максимум
    check_interval = 5   # проверка каждые 5 секунд
    
    # Ждем отключения
    for i in range(max_wait_time // check_interval):
        is_online = await ping_server(server['host'])
        if not is_online:
            break
        await asyncio.sleep(check_interval)
    
    if is_online:
        await message.edit_text("❌ Сервер не отключился в течение ожидаемого времени")
        return
    
    offline_time = time.time()
    await message.edit_text("🔴 Сервер отключился. Ожидаю включения...")
    
    # Ждем включения
    for i in range(max_wait_time // check_interval):
        is_online = await ping_server(server['host'])
        if is_online:
            online_time = time.time()
            reboot_duration = online_time - offline_time
            await message.edit_text(
                f"✅ Сервер перезагрузился!\n"
                f"⏱️ Время перезагрузки: {reboot_duration:.1f} секунд"
            )
            return
        await asyncio.sleep(check_interval)
    
    await message.edit_text("❌ Сервер не включился в течение ожидаемого времени")

# Обновление библиотек
@router.callback_query(F.data.startswith("ssh_update_"))
async def ssh_update(callback_query: CallbackQuery):
    """Обновление библиотек на сервере со сворачиваемым выводом"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    await callback_query.message.edit_text(f"📦 Начинаю обновление библиотек на {server['name']}...")
    
    # Подключаемся если не подключены
    if not ssh_client.is_connected(server_id):
        success, message = await ssh_client.connect(
            server_id=server_id,
            host=server['host'],
            port=server['port'],
            username=server['username'],
            password=server['password']
        )
        if not success:
            await callback_query.message.edit_text(f"❌ Не удалось подключиться: {message}")
            return
    
    # Отправляем команды обновления
    commands = [
        ("sudo apt update", "📥 Обновление списка пакетов"),
        ("sudo apt upgrade -y", "🔄 Обновление пакетов"), 
        ("sudo apt autoremove -y", "🧹 Очистка ненужных пакетов")
    ]
    
    results = []
    
    for cmd, description in commands:
        await callback_query.message.edit_text(f"📦 Выполняю: {description}...")
        success, current_dir, output = await ssh_client.execute_command(server_id, cmd)
        
        results.append({
            'command': cmd,
            'description': description,
            'success': success,
            'output': output or "Нет вывода"
        })
    
    # Формируем сообщение со сворачиваемыми блоками
    text = f"📦 Результат обновления {server['name']}:\n\n"
    
    for i, result in enumerate(results):
        status_emoji = "✅" if result['success'] else "❌"
        text += f"{status_emoji} {result['description']}:\n"
        
        # Создаем сворачиваемый блок
        block_id = f"update_{server_id}_{i}"
        short_output = get_short_output(result['output'])
        
        text += f"<blockquote expandable='{block_id}'>\n"
        text += f"{short_output}\n"
        text += f"</blockquote>\n\n"
    
    # Создаем клавиатуру с кнопками для раскрытия блоков
    keyboard = InlineKeyboardBuilder()
    
    for i, result in enumerate(results):
        block_id = f"update_{server_id}_{i}"
        emoji = "📥" if i == 0 else "🔄" if i == 1 else "🧹"
        keyboard.button(
            text=f"{emoji} Показать вывод {i+1}", 
            callback_data=f"show_output_{server_id}_{i}"
        )
    
    keyboard.button(text="🔄 Обновить", callback_data=f"ssh_update_{server_id}")
    keyboard.button(text="🔙 Назад", callback_data=f"ssh_server_{server_id}")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(
        text,
        reply_markup=keyboard.as_markup(),
        parse_mode="HTML"  # Включаем HTML для блоков
    )

def get_short_output(output: str, max_lines: int = 3) -> str:
    """Получение короткой версии вывода"""
    lines = output.split('\n')
    if len(lines) <= max_lines:
        return output
    
    # Показываем первые и последние строки
    short_lines = lines[:max_lines] + ["...", f"📊 Показано {max_lines} из {len(lines)} строк"]
    return '\n'.join(short_lines)

@router.callback_query(F.data.startswith("show_output_"))
async def show_full_output(callback_query: CallbackQuery):
    """Показать полный вывод команды"""
    try:
        parts = callback_query.data.split("_")
        server_id = int(parts[2])
        command_index = int(parts[3])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    # Здесь нужно получить результаты выполнения команд
    # Для простоты перезапустим обновление или сохраним результаты в состоянии
    await callback_query.answer("ℹ️ Полный вывод доступен в основном сообщении")
    
    # Альтернативно, можно отправить полный вывод отдельным сообщением
    await send_full_output(callback_query.message, server_id, command_index)

async def send_full_output(message: Message, server_id: int, command_index: int):
    """Отправка полного вывода команды"""
    # Команды в том же порядке
    commands_info = [
        ("sudo apt update", "📥 Обновление списка пакетов"),
        ("sudo apt upgrade -y", "🔄 Обновление пакетов"),
        ("sudo apt autoremove -y", "🧹 Очистка ненужных пакетов")
    ]
    
    if command_index >= len(commands_info):
        await message.answer("❌ Неверный индекс команды")
        return
    
    cmd, description = commands_info[command_index]
    
    # Выполняем команду еще раз для получения вывода
    success, current_dir, output = await ssh_client.execute_command(server_id, cmd)
    
    text = f"📦 Полный вывод: {description}\n\n"
    text += f"💻 Команда: <code>{cmd}</code>\n\n"
    
    if output:
        # Форматируем вывод как код
        formatted_output = f"<pre>{output}</pre>"
        
        # Разбиваем длинный вывод на части
        if len(formatted_output) > 4000:
            chunks = [formatted_output[i:i+4000] for i in range(0, len(formatted_output), 4000)]
            for i, chunk in enumerate(chunks):
                await message.answer(
                    f"{text}Часть {i+1}:\n{chunk}",
                    parse_mode="HTML"
                )
        else:
            await message.answer(
                f"{text}{formatted_output}",
                parse_mode="HTML"
            )
    else:
        await message.answer(f"{text}❌ Нет вывода от команды")
        
# Пинг сервера
@router.callback_query(F.data.startswith("ssh_ping_"))
async def ssh_ping(callback_query: CallbackQuery):
    """Пинг SSH сервера с измерением времени"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    await callback_query.message.edit_text(f"🏓 Измеряю пинг до {server['host']}...")
    
    # Измеряем пинг
    success, avg_ping, details = await measure_ping(server['host'])
    
    # Создаем красивый ответ с цветовой индикацией
    if success:
        # Определяем качество соединения по пингу
        if avg_ping < 50:
            quality = "🟢 Отличное"
            emoji = "⚡"
        elif avg_ping < 100:
            quality = "🟡 Хорошее" 
            emoji = "✅"
        elif avg_ping < 200:
            quality = "🟠 Удовлетворительное"
            emoji = "⚠️"
        else:
            quality = "🔴 Плохое"
            emoji = "🐌"
        
        text = f"{emoji} Пинг до {server['name']}\n\n"
        text += f"📍 {server['host']}\n"
        text += f"📊 Качество: {quality}\n"
        text += f"⏱️ Средний пинг: {avg_ping:.1f} мс\n\n"
        text += details
    else:
        text = f"🔴 {server['name']} недоступен\n\n"
        text += f"📍 {server['host']}\n\n"
        text += details
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔄 Измерить снова", callback_data=f"ssh_ping_{server_id}")
    keyboard.button(text="🔙 Назад", callback_data=f"ssh_server_{server_id}")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Закрытие SSH сессии
@router.callback_query(F.data.startswith("ssh_close_"))
async def ssh_close(callback_query: CallbackQuery, state: FSMContext):
    """Закрытие SSH сессии"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    await ssh_close_session(callback_query.message, server_id, state)

async def ssh_close_session(message: Message, server_id: int, state: FSMContext = None):
    """Закрытие SSH сессии"""
    success = await ssh_client.close_connection(server_id)
    
    # Очищаем состояние
    if state:
        await state.clear()
    
    if success:
        await message.answer(
            "✅ SSH сессия закрыта",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔐 SSH Менеджер", callback_data="menu_ssh"),
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_main")
            ]])
        )
    else:
        await message.answer(
            "❌ Ошибка при закрытии сессии",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔐 SSH Менеджер", callback_data="menu_ssh")
            ]])
        )

# Список SSH серверов
@router.callback_query(F.data == "ssh_list_servers")
async def ssh_list_servers(callback_query: CallbackQuery):
    """Список SSH серверов"""
    await callback_query.message.edit_text("📋 Загружаю список серверов...")
    
    servers = await get_ssh_servers()
    
    if not servers:
        text = "📋 Список SSH серверов\n\n📭 Нет сохраненных серверов"
    else:
        text = "📋 Список SSH серверов:\n\n"
        
        # Параллельная проверка статусов
        status_tasks = []
        for server in servers:
            task = get_server_status(server['id'], server['host'])
            status_tasks.append(task)
        
        ping_results = await asyncio.gather(*status_tasks)
        
        for i, server in enumerate(servers):
            # Проверяем пинг из кэша
            is_online = ping_results[i]
            ping_status = "🟢" if is_online else "🔴"
            
            # Статус SSH подключения
            ssh_status = "🟢" if ssh_client.is_connected(server['id']) else "⚪"
            
            text += f"{ssh_status}{ping_status} {server['name']}\n"
            text += f"   Host: {server['host']}:{server['port']}\n"
            text += f"   User: {server['username']}\n\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="➕ Добавить сервер", callback_data="ssh_add_server")
    keyboard.button(text="🔄 Обновить", callback_data="ssh_list_servers")
    keyboard.button(text="🔙 Назад", callback_data="menu_ssh")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data == "ssh_clear_cache")
async def ssh_clear_cache(callback_query: CallbackQuery):
    """Очистка кэша статусов"""
    server_status_cache.clear()
    await callback_query.answer("✅ Кэш статусов очищен")
    await menu_ssh(callback_query)

# Редактирование SSH сервера
@router.callback_query(F.data.startswith("ssh_edit_start_"))
async def ssh_edit_start(callback_query: CallbackQuery, state: FSMContext):
    """Начало редактирования SSH сервера"""
    try:
        server_id = int(callback_query.data.split("_")[3])  # Изменили индекс на 3
    except (IndexError, ValueError) as e:
        print(f"❌ Ошибка парсинга ssh_edit_start: {e}, data: {callback_query.data}")
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    text = f"✏️ Редактирование SSH сервера: {server['name']}\n\n"
    text += f"Выберите поле для редактирования:"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📝 Название", callback_data=f"ssh_edit_name_{server_id}")
    keyboard.button(text="📍 Host", callback_data=f"ssh_edit_host_{server_id}")
    keyboard.button(text="🔢 Port", callback_data=f"ssh_edit_port_{server_id}")
    keyboard.button(text="👤 Пользователь", callback_data=f"ssh_edit_user_{server_id}")
    keyboard.button(text="🔑 Пароль", callback_data=f"ssh_edit_pass_{server_id}")
    keyboard.button(text="🔙 Назад", callback_data=f"ssh_server_{server_id}")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data.startswith("ssh_edit_"))
async def ssh_edit_field(callback_query: CallbackQuery, state: FSMContext):
    """Редактирование конкретного поля SSH сервера"""
    try:
        parts = callback_query.data.split("_")
        
        if len(parts) < 4:
            await callback_query.answer("❌ Неверный формат данных")
            return
            
        field = parts[2]
        server_id = int(parts[3])
        
    except (IndexError, ValueError) as e:
        print(f"❌ Ошибка парсинга ssh_edit_field: {e}, data: {callback_query.data}")
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    field_names = {
        'name': 'название',
        'host': 'host',
        'port': 'порт',
        'user': 'пользователя', 
        'pass': 'пароль'
    }
    
    field_key = {
        'name': 'name',
        'host': 'host', 
        'port': 'port',
        'user': 'username',
        'pass': 'password'
    }
    
    field_display = field_names.get(field)
    field_name = field_key.get(field)
    
    if not field_display:
        await callback_query.answer("❌ Неизвестное поле")
        return
    
    current_value = server.get(field_name, 'не установлено')
    if field_name == 'password':
        current_value = '******'
    
    await state.update_data(
        server_id=server_id,
        field_name=field_name,
        current_server=server
    )
    
    await callback_query.message.edit_text(
        f"✏️ Редактирование SSH сервера\n\nВведите новое значение для {field_display}:\nТекущее значение: {current_value}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"ssh_edit_start_{server_id}")
        ]])
    )
    await state.set_state(EditSSHServer.editing_field)

@router.message(EditSSHServer.editing_field)
async def process_ssh_edit_field(message: Message, state: FSMContext):
    """Обработка редактирования поля SSH сервера"""
    try:
        await message.delete()
    except:
        pass
    
    data = await state.get_data()
    server_id = data['server_id']
    field_name = data['field_name']
    
    new_value = message.text.strip()
    
    if not new_value:
        await message.answer("❌ Значение не может быть пустым")
        return
    
    if field_name == 'port':
        try:
            new_value = int(new_value)
            if not (1 <= new_value <= 65535):
                await message.answer("❌ Порт должен быть в диапазоне 1-65535")
                return
        except ValueError:
            await message.answer("❌ Порт должен быть числом")
            return
    
    success = await update_ssh_server(server_id, {field_name: new_value})
    
    if success:
        await message.answer("✅ Поле успешно обновлено")
        await ssh_server_detail_by_id(message, server_id)
    else:
        await message.answer("❌ Ошибка при обновлении сервера")
    
    await state.clear()

async def ssh_server_detail_by_id(message: Message, server_id: int):
    """Показать детальную информацию о сервере по ID"""
    server = await get_ssh_server(server_id)
    if not server:
        await message.answer("❌ SSH сервер не найден")
        return
    
    is_online = await ping_server(server['host'])
    ping_status = "🟢 Онлайн" if is_online else "🔴 Офлайн"
    
    ssh_connected = ssh_client.is_connected(server_id)
    ssh_status = "🟢 Подключен" if ssh_connected else "⚪ Не подключен"
    
    text = f"🔐 SSH Сервер: {server['name']}\n\n"
    text += f"📍 Host: {server['host']}\n"
    text += f"🔢 Port: {server['port']}\n"
    text += f"👤 User: {server['username']}\n"
    text += f"📊 Статус: {ping_status} | {ssh_status}\n\n"
    text += "Выберите действие:"
    
    keyboard = InlineKeyboardBuilder()
    
    keyboard.button(text="🔌 Подключиться", callback_data=f"ssh_connect_{server_id}")
    keyboard.button(text="🔄 Перезагрузить", callback_data=f"ssh_reboot_{server_id}")
    keyboard.button(text="📦 Обновить библиотеки", callback_data=f"ssh_update_{server_id}")
    keyboard.button(text="🏓 Пинг", callback_data=f"ssh_ping_{server_id}")
    
    keyboard.button(text="✏️ Редактировать", callback_data=f"ssh_edit_start_{server_id}")
    keyboard.button(text="🗑️ Удалить", callback_data=f"ssh_delete_{server_id}")
    
    keyboard.button(text="🔙 Назад", callback_data="menu_ssh")
    keyboard.adjust(1)
    
    await message.answer(text, reply_markup=keyboard.as_markup())

# Удаление SSH сервера
@router.callback_query(F.data.startswith("ssh_delete_"))
async def ssh_delete(callback_query: CallbackQuery):
    """Удаление SSH сервера"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    # Закрываем соединение если открыто
    if ssh_client.is_connected(server_id):
        await ssh_client.close_connection(server_id)
    
    text = f"❌ Удаление SSH сервера\n\nВы уверены, что хотите удалить сервер?\n\nИмя: {server['name']}\nHost: {server['host']}\n\nЭто действие нельзя отменить!"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, удалить", callback_data=f"ssh_confirm_delete_{server_id}")
    keyboard.button(text="❌ Нет, отмена", callback_data=f"ssh_server_{server_id}")
    keyboard.adjust(2)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data.startswith("ssh_confirm_delete_"))
async def ssh_confirm_delete(callback_query: CallbackQuery):
    """Подтверждение удаления SSH сервера"""
    try:
        server_id = int(callback_query.data.split("_")[3])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_ssh_server(server_id)
    if not server:
        await callback_query.answer("❌ SSH сервер не найден")
        return
    
    success = await delete_ssh_server(server_id)
    
    if success:
        await callback_query.message.edit_text(
            f"✅ SSH сервер '{server['name']}' успешно удален",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔐 SSH Менеджер", callback_data="menu_ssh"),
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_main")
            ]])
        )
    else:
        await callback_query.message.edit_text(
            "❌ Ошибка при удалении сервера",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"ssh_server_{server_id}")
            ]])
        )