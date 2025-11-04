import os
import asyncio
from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.db import (
    add_connection, get_connections, get_connection,
    update_connection_enabled, delete_connection, get_recent_logs,
    update_connection, get_enabled_backup_server
)
from utils.connection_test import test_connection

router = Router()

# Проверка прав администратора
def is_admin(user_id: int) -> bool:
    admin_id = os.getenv('ADMIN_ID')
    if not admin_id:
        return False
    return user_id == int(admin_id)

# Классы состояний для FSM
class AddConnection(StatesGroup):
    choosing_db_type = State()
    entering_name = State()
    entering_host = State()
    entering_port = State()
    entering_database = State()
    entering_user = State()
    entering_password = State()
    entering_file_path = State()
    ssh_required = State()
    ssh_host = State()
    ssh_port = State()
    ssh_user = State()
    ssh_password = State()
    confirmation = State()

class EditConnection(StatesGroup):
    choosing_field = State()
    editing_field = State()

# Главное меню
def get_main_menu_keyboard():
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="📊 Список подключений", callback_data="menu_connections")
    keyboard.button(text="➕ Добавить подключение", callback_data="menu_add_connection")
    keyboard.button(text="🔄 Сделать бэкап", callback_data="menu_backup")
    keyboard.button(text="📁 Менеджер бэкапов", callback_data="menu_backup_manager")
    keyboard.button(text="🔐 SSH", callback_data="menu_ssh")  # Новая кнопка
    keyboard.button(text="⚙️ Настройки автобэкапа", callback_data="menu_autobackup")
    keyboard.button(text="📋 Логи бэкапов", callback_data="menu_logs")
    keyboard.adjust(1)
    return keyboard.as_markup()

async def show_main_menu(callback_query: CallbackQuery = None, message: Message = None, state: FSMContext = None):
    """Показать главное меню"""
    if state:
        await state.clear()
    
    text = "🤖 Бот для бэкапов баз данных\n\nВыберите действие:"
    keyboard = get_main_menu_keyboard()
    
    if callback_query:
        await callback_query.message.edit_text(text, reply_markup=keyboard)
    elif message:
        await message.answer(text, reply_markup=keyboard)

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа к этому боту")
        return
    
    await show_main_menu(message=message, state=state)

@router.callback_query(F.data == "menu_main")
async def menu_main(callback_query: CallbackQuery, state: FSMContext):
    await show_main_menu(callback_query=callback_query, state=state)

# Меню подключений
@router.callback_query(F.data == "menu_connections")
async def menu_connections(callback_query: CallbackQuery, state: FSMContext):
    connections = await get_connections()
    
    if not connections:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="➕ Добавить подключение", callback_data="menu_add_connection")
        keyboard.button(text="🔙 Назад", callback_data="menu_main")
        keyboard.adjust(1)
        
        await callback_query.message.edit_text(
            "📊 Список подключений\n\n📭 Нет сохраненных подключений",
            reply_markup=keyboard.as_markup()
        )
        return
    
    text = "📊 Список подключений:\n\n"
    for conn in connections:
        status = "✅" if conn['enabled'] else "❌"
        db_info = conn['database'] or conn['file_path'] or 'N/A'
        text += f"{status} {conn['name']} ({conn['db_type']})\n"
        text += f"   ID: {conn['id']} | БД: {db_info}\n\n"
    
    keyboard = InlineKeyboardBuilder()
    for conn in connections:
        keyboard.button(text=f"✏️ {conn['name']}", callback_data=f"conn_edit_{conn['id']}")
    keyboard.button(text="🔙 Назад", callback_data="menu_main")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Меню редактирования подключения
@router.callback_query(F.data.startswith("conn_edit_"))
async def conn_edit(callback_query: CallbackQuery, state: FSMContext):
    try:
        connection_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    text = f"✏️ Редактирование подключения:\n\n"
    text += f"Имя: {connection['name']}\n"
    text += f"Тип: {connection['db_type']}\n"
    
    if connection['db_type'] != 'sqlite':
        text += f"Host: {connection['host']}\n"
        text += f"Port: {connection['port']}\n"
        text += f"Database: {connection['database']}\n"
        text += f"User: {connection['user']}\n"
        text += "Password: ******\n"
    else:
        if connection.get('ssh_host'):
            text += f"SSH Host: {connection['ssh_host']}\n"
            text += f"SSH Port: {connection.get('ssh_port', 22)}\n"
            text += f"SSH User: {connection['ssh_user']}\n"
            text += "SSH Password: ******\n"
        text += f"File Path: {connection['file_path']}\n"
    
    text += f"Автобэкап: {'✅ Включен' if connection['enabled'] else '❌ Выключен'}\n\n"
    text += "Выберите действие:"
    
    keyboard = InlineKeyboardBuilder()
    
    if connection['db_type'] != 'sqlite':
        keyboard.button(text="🖥️ Host", callback_data=f"edit_host_{connection_id}")
        keyboard.button(text="🔢 Port", callback_data=f"edit_port_{connection_id}")
        keyboard.button(text="🗃️ Database", callback_data=f"edit_db_{connection_id}")
        keyboard.button(text="👤 User", callback_data=f"edit_user_{connection_id}")
        keyboard.button(text="🔑 Password", callback_data=f"edit_pass_{connection_id}")
    else:
        keyboard.button(text="📁 File Path", callback_data=f"edit_file_{connection_id}")
    
    keyboard.button(text="📝 Name", callback_data=f"edit_name_{connection_id}")
    keyboard.button(text="🔗 Проверить подключение", callback_data=f"test_{connection_id}")
    keyboard.button(text="🔄 Автобэкап", callback_data=f"toggle_{connection_id}")
    keyboard.button(text="❌ Удалить", callback_data=f"del_confirm_{connection_id}")
    keyboard.button(text="🔙 Назад", callback_data="menu_connections")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Добавление подключения
@router.callback_query(F.data == "menu_add_connection")
async def menu_add_connection(callback_query: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="PostgreSQL", callback_data="db_psql")
    keyboard.button(text="MySQL", callback_data="db_mysql")
    keyboard.button(text="SQLite", callback_data="db_sqlite")
    keyboard.button(text="MongoDB", callback_data="db_mongo")
    keyboard.button(text="🔙 Назад", callback_data="menu_main")
    keyboard.adjust(2)
    
    await callback_query.message.edit_text(
        "➕ Добавление подключения\n\nВыберите тип базы данных:",
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(AddConnection.choosing_db_type)

@router.callback_query(AddConnection.choosing_db_type, F.data.startswith("db_"))
async def process_db_type(callback_query: CallbackQuery, state: FSMContext):
    db_type_map = {
        'db_psql': 'psql',
        'db_mysql': 'mysql', 
        'db_sqlite': 'sqlite',
        'db_mongo': 'mongo'
    }
    
    db_type = db_type_map.get(callback_query.data)
    if not db_type:
        await callback_query.answer("Неизвестный тип БД")
        return
    
    await state.update_data(
        db_type=db_type,
        bot_message_id=callback_query.message.message_id
    )
    
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({db_type})\n\nВведите имя подключения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_add_connection")
        ]])
    )
    await state.set_state(AddConnection.entering_name)

@router.message(AddConnection.entering_name)
async def process_name(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except:
        pass
    
    if message.text == '/cancel':
        await show_main_menu(message=message, state=state)
        return
    
    await state.update_data(name=message.text)
    data = await state.get_data()
    
    if data['db_type'] == 'sqlite':
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="✅ Да, требуется SSH", callback_data="ssh_yes")
        keyboard.button(text="❌ Нет, локальный файл", callback_data="ssh_no")
        keyboard.button(text="🔙 Назад", callback_data="menu_add_connection")
        keyboard.adjust(1)
        
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_message_id,
            text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {message.text}\n\nТребуется ли SSH подключение?",
            reply_markup=keyboard.as_markup()
        )
        await state.set_state(AddConnection.ssh_required)
    else:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_message_id,
            text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {message.text}\n\nВведите host:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="menu_add_connection")
            ]])
        )
        await state.set_state(AddConnection.entering_host)

# Остальные обработчики для добавления подключения (аналогично предыдущей версии, но с редактированием сообщения)
@router.callback_query(AddConnection.ssh_required, F.data == "ssh_yes")
async def process_ssh_required(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH: Требуется\n\nВведите SSH host:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_name")
        ]])
    )
    await state.set_state(AddConnection.ssh_host)

@router.callback_query(AddConnection.ssh_required, F.data == "ssh_no")
async def process_ssh_not_required(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH: Не требуется\n\nВведите путь к файлу:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_name")
        ]])
    )
    await state.set_state(AddConnection.entering_file_path)

@router.callback_query(AddConnection.ssh_required, F.data == "back_to_name")
async def back_to_name(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\nВведите имя подключения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_add_connection")
        ]])
    )
    await state.set_state(AddConnection.entering_name)

@router.message(AddConnection.ssh_host)
async def process_ssh_host(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(ssh_host=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {message.text}\n\nВведите SSH порт (по умолчанию 22):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_required")
        ]])
    )
    await state.set_state(AddConnection.ssh_port)

# Добавляем после process_ssh_host

@router.message(AddConnection.ssh_port)
async def process_ssh_port(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    try:
        ssh_port = int(message.text) if message.text else 22
        await state.update_data(ssh_port=ssh_port)
        
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_message_id,
            text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n✅ SSH порт: {ssh_port}\n\nВведите SSH пользователя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_host")
            ]])
        )
        await state.set_state(AddConnection.ssh_user)
    except ValueError:
        await message.answer("❌ Порт должен быть числом. Попробуйте еще раз:")

@router.callback_query(AddConnection.ssh_port, F.data == "back_to_ssh_host")
async def back_to_ssh_host(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n\nВведите SSH порт (по умолчанию 22):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_required")
        ]])
    )
    await state.set_state(AddConnection.ssh_port)

@router.message(AddConnection.ssh_user)
async def process_ssh_user(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(ssh_user=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n✅ SSH порт: {data['ssh_port']}\n✅ SSH пользователь: {message.text}\n\nВведите SSH пароль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_port")
        ]])
    )
    await state.set_state(AddConnection.ssh_password)

@router.callback_query(AddConnection.ssh_user, F.data == "back_to_ssh_port")
async def back_to_ssh_port(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n✅ SSH порт: {data['ssh_port']}\n\nВведите SSH пользователя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_host")
        ]])
    )
    await state.set_state(AddConnection.ssh_user)

@router.message(AddConnection.ssh_password)
async def process_ssh_password(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(ssh_password=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n✅ SSH порт: {data['ssh_port']}\n✅ SSH пользователь: {data['ssh_user']}\n✅ SSH пароль: ******\n\nВведите путь к файлу SQLite на сервере:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_user")
        ]])
    )
    await state.set_state(AddConnection.entering_file_path)

@router.callback_query(AddConnection.ssh_password, F.data == "back_to_ssh_user")
async def back_to_ssh_user(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n✅ SSH порт: {data['ssh_port']}\n✅ SSH пользователь: {data['ssh_user']}\n\nВведите SSH пароль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_port")
        ]])
    )
    await state.set_state(AddConnection.ssh_password)

@router.message(AddConnection.entering_file_path)
async def process_file_path(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(file_path=message.text)
    data = await state.get_data()
    
    await show_confirmation(message, data, state)

@router.callback_query(AddConnection.entering_file_path, F.data == "back_to_ssh_password")
async def back_to_ssh_password(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n✅ SSH порт: {data['ssh_port']}\n✅ SSH пользователь: {data['ssh_user']}\n✅ SSH пароль: ******\n\nВведите путь к файлу SQLite на сервере:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_user")
        ]])
    )
    await state.set_state(AddConnection.entering_file_path)

# Обработчики для обычных БД (PostgreSQL, MySQL, MongoDB)
@router.message(AddConnection.entering_host)
async def process_host(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(host=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {message.text}\n\nВведите порт:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_name_regular")
        ]])
    )
    await state.set_state(AddConnection.entering_port)

@router.callback_query(AddConnection.entering_host, F.data == "back_to_name_regular")
async def back_to_name_regular(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\nВведите имя подключения:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_add_connection")
        ]])
    )
    await state.set_state(AddConnection.entering_name)

@router.message(AddConnection.entering_port)
async def process_port(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    try:
        port = int(message.text)
        await state.update_data(port=port)
        
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=bot_message_id,
            text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {port}\n\nВведите имя базы данных:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_host")
            ]])
        )
        await state.set_state(AddConnection.entering_database)
    except ValueError:
        await message.answer("❌ Порт должен быть числом. Попробуйте еще раз:")

@router.callback_query(AddConnection.entering_port, F.data == "back_to_host")
async def back_to_host(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n\nВведите порт:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_name_regular")
        ]])
    )
    await state.set_state(AddConnection.entering_port)

@router.message(AddConnection.entering_database)
async def process_database(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(database=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ База данных: {message.text}\n\nВведите имя пользователя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_port")
        ]])
    )
    await state.set_state(AddConnection.entering_user)

@router.callback_query(AddConnection.entering_database, F.data == "back_to_port")
async def back_to_port(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n\nВведите имя базы данных:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_host")
        ]])
    )
    await state.set_state(AddConnection.entering_database)

@router.message(AddConnection.entering_user)
async def process_user(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(user=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ База данных: {data['database']}\n✅ Пользователь: {message.text}\n\nВведите пароль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_database")
        ]])
    )
    await state.set_state(AddConnection.entering_password)

@router.callback_query(AddConnection.entering_user, F.data == "back_to_database")
async def back_to_database(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ База данных: {data['database']}\n\nВведите имя пользователя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_port")
        ]])
    )
    await state.set_state(AddConnection.entering_user)

@router.message(AddConnection.entering_password)
async def process_password(message: Message, state: FSMContext):
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(password=message.text)
    data = await state.get_data()
    
    await show_confirmation(message, data, state)

@router.callback_query(AddConnection.entering_password, F.data == "back_to_user")
async def back_to_user(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ База данных: {data['database']}\n✅ Пользователь: {data['user']}\n\nВведите пароль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_database")
        ]])
    )
    await state.set_state(AddConnection.entering_password)

async def show_confirmation(message: Message, data: dict, state: FSMContext):
    """Показать подтверждение данных подключения"""
    bot_message_id = data.get('bot_message_id')
    
    text = "📋 Проверьте данные подключения:\n\n"
    text += f"Тип: {data['db_type']}\n"
    text += f"Имя: {data['name']}\n"
    
    if data['db_type'] != 'sqlite':
        text += f"Host: {data['host']}\n"
        text += f"Port: {data['port']}\n"
        text += f"База данных: {data['database']}\n"
        text += f"Пользователь: {data['user']}\n"
        text += "Пароль: ******\n"
    else:
        if 'ssh_host' in data:
            text += f"SSH Host: {data['ssh_host']}\n"
            text += f"SSH Port: {data.get('ssh_port', 22)}\n"
            text += f"SSH User: {data['ssh_user']}\n"
            text += "SSH Password: ******\n"
        text += f"Путь к файлу: {data.get('file_path', 'не указан')}\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Подтвердить", callback_data="confirm")
    keyboard.button(text="🔗 Проверить подключение", callback_data="test_before_save")
    if data['db_type'] != 'sqlite':
        keyboard.button(text="🔙 Назад", callback_data="back_to_password")
    else:
        keyboard.button(text="🔙 Назад", callback_data="back_to_file_path")
    keyboard.adjust(1)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=text,
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(AddConnection.confirmation)

@router.callback_query(AddConnection.confirmation, F.data == "back_to_password")
async def back_to_password(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ База данных: {data['database']}\n✅ Пользователь: {data['user']}\n\nВведите пароль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_user")
        ]])
    )
    await state.set_state(AddConnection.entering_password)

@router.callback_query(AddConnection.confirmation, F.data == "back_to_file_path")
async def back_to_file_path(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if 'ssh_host' in data:
        await callback_query.message.edit_text(
            f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n✅ SSH host: {data['ssh_host']}\n✅ SSH порт: {data['ssh_port']}\n✅ SSH пользователь: {data['ssh_user']}\n✅ SSH пароль: ******\n\nВведите путь к файлу SQLite на сервере:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_password")
            ]])
        )
    else:
        await callback_query.message.edit_text(
            f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n\nВведите путь к файлу:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_ssh_required")
            ]])
        )
    await state.set_state(AddConnection.entering_file_path)

@router.callback_query(AddConnection.confirmation, F.data == "test_before_save")
async def test_before_save(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    # Создаем временный объект подключения для теста
    test_conn = {
        'name': data['name'],
        'db_type': data['db_type'],
        'host': data.get('host'),
        'port': data.get('port'),
        'database': data.get('database'),
        'user': data.get('user'),
        'password': data.get('password'),
        'file_path': data.get('file_path'),
        'ssh_host': data.get('ssh_host'),
        'ssh_port': data.get('ssh_port'),
        'ssh_user': data.get('ssh_user'),
        'ssh_password': data.get('ssh_password')
    }
    
    await callback_query.message.edit_text(f"🔍 Проверяю подключение...")
    
    success, message = await test_connection(test_conn)
    
    if success:
        text = f"✅ Подключение успешно!\n\n{message}\n\nСохранить подключение?"
    else:
        text = f"❌ Ошибка подключения:\n\n{message}\n\nВсе равно сохранить подключение?"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, сохранить", callback_data="confirm")
    keyboard.button(text="✏️ Редактировать", callback_data="edit_before_save")
    keyboard.button(text="🔙 Назад", callback_data="back_to_confirmation")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(AddConnection.confirmation, F.data == "back_to_confirmation")
async def back_to_confirmation(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await show_confirmation_message(callback_query.message, data, state)

async def show_confirmation_message(message: Message, data: dict, state: FSMContext):
    """Показать сообщение подтверждения"""
    text = "📋 Проверьте данные подключения:\n\n"
    text += f"Тип: {data['db_type']}\n"
    text += f"Имя: {data['name']}\n"
    
    if data['db_type'] != 'sqlite':
        text += f"Host: {data['host']}\n"
        text += f"Port: {data['port']}\n"
        text += f"База данных: {data['database']}\n"
        text += f"Пользователь: {data['user']}\n"
        text += "Пароль: ******\n"
    else:
        if 'ssh_host' in data:
            text += f"SSH Host: {data['ssh_host']}\n"
            text += f"SSH Port: {data.get('ssh_port', 22)}\n"
            text += f"SSH User: {data['ssh_user']}\n"
            text += "SSH Password: ******\n"
        text += f"Путь к файлу: {data.get('file_path', 'не указан')}\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Подтвердить", callback_data="confirm")
    keyboard.button(text="🔗 Проверить подключение", callback_data="test_before_save")
    if data['db_type'] != 'sqlite':
        keyboard.button(text="🔙 Назад", callback_data="back_to_password")
    else:
        keyboard.button(text="🔙 Назад", callback_data="back_to_file_path")
    keyboard.adjust(1)
    
    await message.edit_text(text, reply_markup=keyboard.as_markup())
    await state.set_state(AddConnection.confirmation)

@router.callback_query(AddConnection.confirmation, F.data == "confirm")
async def process_confirmation(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    try:
        # Подготавливаем параметры для функции
        connection_params = {
            'name': data['name'],
            'db_type': data['db_type'],
            'host': data.get('host'),
            'port': data.get('port'),
            'database': data.get('database'),
            'user': data.get('user'),
            'password': data.get('password'),
            'file_path': data.get('file_path'),
            'ssh_host': data.get('ssh_host'),
            'ssh_port': data.get('ssh_port', 22),
            'ssh_user': data.get('ssh_user'),
            'ssh_password': data.get('ssh_password'),
            'enabled': True
        }
        
        # Удаляем None значения для SQLite
        if data['db_type'] == 'sqlite':
            connection_params['host'] = None
            connection_params['port'] = None
            connection_params['database'] = None
            connection_params['user'] = None
            connection_params['password'] = None
        else:
            connection_params['file_path'] = None
            # Для не-SQLite БД очищаем SSH параметры, если они были введены по ошибке
            connection_params['ssh_host'] = None
            connection_params['ssh_port'] = None
            connection_params['ssh_user'] = None
            connection_params['ssh_password'] = None
        
        connection_id = await add_connection(**connection_params)
        
        await callback_query.message.edit_text(
            f"✅ Подключение '{data['name']}' успешно добавлено (ID: {connection_id})",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📊 Список подключений", callback_data="menu_connections"),
                InlineKeyboardButton(text="➕ Добавить еще", callback_data="menu_add_connection")
            ], [
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_main")
            ]])
        )
        
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ Ошибка при добавлении подключения: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_confirmation")
            ]])
        )
    
    await state.clear()

@router.callback_query(AddConnection.ssh_required, F.data == "back_to_ssh_required")
async def back_to_ssh_required(callback_query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, требуется SSH", callback_data="ssh_yes")
    keyboard.button(text="❌ Нет, локальный файл", callback_data="ssh_no")
    keyboard.button(text="🔙 Назад", callback_data="back_to_name")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(
        f"➕ Добавление подключения ({data['db_type']})\n\n✅ Имя: {data['name']}\n\nТребуется ли SSH подключение?",
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(AddConnection.ssh_required)

@router.callback_query(F.data == "menu_backup")
async def menu_backup(callback_query: CallbackQuery):
    connections = await get_connections()
    
    if not connections:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="➕ Добавить подключение", callback_data="menu_add_connection")
        keyboard.button(text="🔙 Назад", callback_data="menu_main")
        keyboard.adjust(1)
        
        await callback_query.message.edit_text(
            "🔄 Сделать бэкап\n\n📭 Нет доступных подключений",
            reply_markup=keyboard.as_markup()
        )
        return
    
    text = "🔄 Сделать бэкап\n\nВыберите подключение для бэкапа:"
    
    keyboard = InlineKeyboardBuilder()
    for conn in connections:
        keyboard.button(text=f"{conn['name']} ({conn['db_type']})", callback_data=f"backup_{conn['id']}")
    keyboard.button(text="📁 Менеджер бэкапов", callback_data="menu_backup_manager")
    keyboard.button(text="🔙 Назад", callback_data="menu_main")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Меню автобэкапа
@router.callback_query(F.data == "menu_autobackup")
async def menu_autobackup(callback_query: CallbackQuery):
    connections = await get_connections()
    
    if not connections:
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="➕ Добавить подключение", callback_data="menu_add_connection")
        keyboard.button(text="🔙 Назад", callback_data="menu_main")
        keyboard.adjust(1)
        
        await callback_query.message.edit_text(
            "⚙️ Настройки автобэкапа\n\n📭 Нет доступных подключений",
            reply_markup=keyboard.as_markup()
        )
        return
    
    text = "⚙️ Настройки автобэкапа\n\nАвтобэкап выполняется ежедневно в 02:00\n\nСтатус подключений:\n"
    
    for conn in connections:
        status = "✅" if conn['enabled'] else "❌"
        text += f"{status} {conn['name']}\n"
    
    # Добавляем информацию о резервном сервере
    backup_server = await get_enabled_backup_server()
    if backup_server:
        text += f"\n📦 Резервный сервер: ✅ {backup_server['name']}"
    else:
        text += f"\n📦 Резервный сервер: ❌ Не настроен"
    
    keyboard = InlineKeyboardBuilder()
    
    for conn in connections:
        status = "🔴 Выключить" if conn['enabled'] else "🟢 Включить"
        keyboard.button(text=f"{status} {conn['name']}", callback_data=f"autobackup_toggle_{conn['id']}")
    
    # Добавляем кнопку снапшота
    keyboard.button(text="📦 Снапшот", callback_data="menu_snapshot")
    keyboard.button(text="🔙 Назад", callback_data="menu_main")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Меню логов
@router.callback_query(F.data == "menu_logs")
async def menu_logs(callback_query: CallbackQuery):
    logs = await get_recent_logs(10)
    
    if not logs:
        text = "📋 Логи бэкапов\n\n📭 Нет записей в логах"
    else:
        text = "📋 Последние 10 бэкапов:\n\n"
        for log in logs:
            status = "✅" if log['success'] else "❌"
            timestamp = log['created_at'][:19] if log['created_at'] else "N/A"
            text += f"{status} {log['connection_name']}\n"
            text += f"   {timestamp}\n"
            if not log['success'] and log['error_message']:
                error_short = log['error_message'][:50] + "..." if len(log['error_message']) > 50 else log['error_message']
                text += f"   Ошибка: {error_short}\n"
            text += "\n"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data="menu_main")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Обработчики для остальных функций (тестирование, удаление и т.д.)
@router.callback_query(F.data.startswith("test_"))
async def test_connection_handler(callback_query: CallbackQuery):
    try:
        connection_id = int(callback_query.data.split("_")[1])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    await callback_query.message.edit_text(f"🔍 Проверяю подключение к {connection['name']}...")
    
    success, message = await test_connection(connection)
    
    if success:
        text = f"✅ Подключение к {connection['name']} успешно!\n\n{message}"
    else:
        text = f"❌ Ошибка подключения к {connection['name']}:\n\n{message}"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="🔙 Назад", callback_data=f"conn_edit_{connection_id}")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data.startswith("del_confirm_"))
async def del_confirm(callback_query: CallbackQuery):
    try:
        connection_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    text = f"❌ Удаление подключения\n\nВы уверены, что хотите удалить подключение?\n\nИмя: {connection['name']}\nТип: {connection['db_type']}\n\nЭто действие нельзя отменить!"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, удалить", callback_data=f"delete_{connection_id}")
    keyboard.button(text="❌ Нет, отмена", callback_data=f"conn_edit_{connection_id}")
    keyboard.adjust(2)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data.startswith("delete_"))
async def delete_connection_handler(callback_query: CallbackQuery):
    try:
        connection_id = int(callback_query.data.split("_")[1])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    # Подтверждение удаления с кнопками
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, удалить", callback_data=f"confirm_del_{connection_id}")
    keyboard.button(text="❌ Нет, отмена", callback_data=f"conn_edit_{connection_id}")
    keyboard.adjust(2)
    
    await callback_query.message.edit_text(
        f"⚠️ Вы уверены, что хотите удалить подключение?\n\nИмя: {connection['name']}\nТип: {connection['db_type']}\n\nЭто действие нельзя отменить!",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data.startswith("confirm_del_"))
async def confirm_delete_connection(callback_query: CallbackQuery):
    try:
        connection_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    success = await delete_connection(connection_id)
    
    if success:
        # Обновляем сообщение вместо показа уведомления
        await callback_query.message.edit_text(
            f"✅ Подключение '{connection['name']}' успешно удалено",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📊 Список подключений", callback_data="menu_connections"),
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_main")
            ]])
        )
    else:
        await callback_query.message.edit_text(
            "❌ Ошибка при удалении подключения",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"conn_edit_{connection_id}")
            ]])
        )

@router.callback_query(F.data.startswith("toggle_"))
async def toggle_handler(callback_query: CallbackQuery):
    try:
        connection_id = int(callback_query.data.split("_")[1])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    new_status = not connection['enabled']
    await update_connection_enabled(connection_id, new_status)
    
    await callback_query.answer(f"Автобэкап {'включен' if new_status else 'выключен'}")
    await conn_edit(callback_query)

# Добавляем обработчики редактирования полей

@router.callback_query(F.data.startswith("edit_"))
async def edit_field_start(callback_query: CallbackQuery, state: FSMContext):
    try:
        field_type = callback_query.data.split("_")[1]
        connection_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    field_names = {
        'name': 'имя',
        'host': 'host',
        'port': 'порт', 
        'db': 'базу данных',
        'user': 'пользователя',
        'pass': 'пароль',
        'file': 'путь к файлу'
    }
    
    field_key = {
        'name': 'name',
        'host': 'host',
        'port': 'port',
        'db': 'database',
        'user': 'user',
        'pass': 'password',
        'file': 'file_path'
    }
    
    field_display = field_names.get(field_type)
    field_name = field_key.get(field_type)
    
    if not field_display:
        await callback_query.answer("❌ Неизвестное поле")
        return
    
    current_value = connection.get(field_name, 'не установлено')
    if field_name == 'password':
        current_value = '******'
    
    await state.update_data(
        connection_id=connection_id,
        field_name=field_name,
        current_connection=connection
    )
    
    await callback_query.message.edit_text(
        f"✏️ Редактирование подключения\n\nВведите новое значение для {field_display}:\nТекущее значение: {current_value}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"conn_edit_{connection_id}")
        ]])
    )
    await state.set_state(EditConnection.editing_field)

@router.message(EditConnection.editing_field)
async def process_edit_field(message: Message, state: FSMContext):
    # Удаляем сообщение пользователя
    try:
        await message.delete()
    except:
        pass
    
    data = await state.get_data()
    connection_id = data['connection_id']
    field_name = data['field_name']
    
    new_value = message.text
    
    # Валидация порта
    if field_name == 'port':
        try:
            new_value = int(new_value)
        except ValueError:
            await message.answer("❌ Порт должен быть числом. Попробуйте еще раз:")
            return
    
    # Обновление подключения
    success = await update_connection(connection_id, {field_name: new_value})
    
    if success:
        await message.answer("✅ Поле успешно обновлено")
        await conn_edit_by_id(message, connection_id)
    else:
        await message.answer("❌ Ошибка при обновлении подключения")
    
    await state.clear()

async def conn_edit_by_id(message: Message, connection_id: int):
    """Показать меню редактирования по ID"""
    connection = await get_connection(connection_id)
    if not connection:
        await message.answer("❌ Подключение не найдено")
        return
    
    text = f"✏️ Редактирование подключения:\n\n"
    text += f"Имя: {connection['name']}\n"
    text += f"Тип: {connection['db_type']}\n"
    
    if connection['db_type'] != 'sqlite':
        text += f"Host: {connection['host']}\n"
        text += f"Port: {connection['port']}\n"
        text += f"Database: {connection['database']}\n"
        text += f"User: {connection['user']}\n"
        text += "Password: ******\n"
    else:
        if connection.get('ssh_host'):
            text += f"SSH Host: {connection['ssh_host']}\n"
            text += f"SSH Port: {connection.get('ssh_port', 22)}\n"
            text += f"SSH User: {connection['ssh_user']}\n"
            text += "SSH Password: ******\n"
        text += f"File Path: {connection['file_path']}\n"
    
    text += f"Автобэкап: {'✅ Включен' if connection['enabled'] else '❌ Выключен'}\n\n"
    text += "Выберите действие:"
    
    keyboard = InlineKeyboardBuilder()
    
    if connection['db_type'] != 'sqlite':
        keyboard.button(text="🖥️ Host", callback_data=f"edit_host_{connection_id}")
        keyboard.button(text="🔢 Port", callback_data=f"edit_port_{connection_id}")
        keyboard.button(text="🗃️ Database", callback_data=f"edit_db_{connection_id}")
        keyboard.button(text="👤 User", callback_data=f"edit_user_{connection_id}")
        keyboard.button(text="🔑 Password", callback_data=f"edit_pass_{connection_id}")
    else:
        keyboard.button(text="📁 File Path", callback_data=f"edit_file_{connection_id}")
    
    keyboard.button(text="📝 Name", callback_data=f"edit_name_{connection_id}")
    keyboard.button(text="🔗 Проверить подключение", callback_data=f"test_{connection_id}")
    keyboard.button(text="🔄 Автобэкап", callback_data=f"toggle_{connection_id}")
    keyboard.button(text="❌ Удалить", callback_data=f"del_confirm_{connection_id}")
    keyboard.button(text="🔙 Назад", callback_data="menu_connections")
    keyboard.adjust(1)
    
    await message.answer(text, reply_markup=keyboard.as_markup())