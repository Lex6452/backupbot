import os
import asyncio
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.db import (
    add_backup_server, get_backup_servers, get_backup_server,
    update_backup_server, delete_backup_server, get_enabled_backup_server
)
from utils.backup_transfer import backup_transfer
from utils.ssh_utils import ping_server

router = Router()

# Проверка прав администратора
def is_admin(user_id: int) -> bool:
    admin_id = os.getenv('ADMIN_ID')
    if not admin_id:
        return False
    return user_id == int(admin_id)

# Классы состояний для FSM
class AddBackupServer(StatesGroup):
    entering_name = State()
    entering_host = State()
    entering_port = State()
    entering_username = State()
    entering_password = State()
    entering_remote_path = State()
    confirmation = State()

class EditBackupServer(StatesGroup):
    choosing_field = State()
    editing_field = State()

# Главное меню снапшотов
@router.callback_query(F.data == "menu_snapshot")
async def menu_snapshot(callback_query: CallbackQuery, state: FSMContext):
    """Главное меню управления резервными серверами"""
    if not is_admin(callback_query.from_user.id):
        await callback_query.answer("⛔ У вас нет доступа")
        return
    
    backup_servers = await get_backup_servers()
    enabled_server = await get_enabled_backup_server()
    
    if not backup_servers:
        # Нет серверов - предлагаем добавить
        text = "📦 Управление резервными серверами\n\n"
        text += "📭 Резервные серверы не настроены\n\n"
        text += "Резервные серверы используются для автоматического копирования бэкапов на удаленный сервер."
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="➕ Добавить сервер", callback_data="snapshot_add_server")
        keyboard.button(text="🔙 Назад", callback_data="menu_autobackup")
        keyboard.adjust(1)
        
    else:
        # Есть серверы - показываем управление
        text = "📦 Управление резервными серверами\n\n"
        
        for server in backup_servers:
            status = "🟢" if server['enabled'] else "🔴"
            text += f"{status} {server['name']}\n"
            text += f"   📍 {server['host']}:{server['port']}\n"
            text += f"   📁 {server['remote_path']}\n\n"
        
        if enabled_server:
            text += f"✅ Активный сервер: {enabled_server['name']}"
        else:
            text += "❌ Нет активного резервного сервера"
        
        keyboard = InlineKeyboardBuilder()
        keyboard.button(text="📋 Резерватор", callback_data="snapshot_browser")
        keyboard.button(text="➕ Добавить сервер", callback_data="snapshot_add_server")
        
        for server in backup_servers:
            keyboard.button(text=f"⚙️ {server['name']}", callback_data=f"snapshot_server_{server['id']}")
        
        keyboard.button(text="🔙 Назад", callback_data="menu_autobackup")
        keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Добавление резервного сервера
@router.callback_query(F.data == "snapshot_add_server")
async def snapshot_add_server(callback_query: CallbackQuery, state: FSMContext):
    """Начало добавления резервного сервера"""
    await state.update_data(bot_message_id=callback_query.message.message_id)
    
    await callback_query.message.edit_text(
        "➕ Добавление резервного сервера\n\nВведите название сервера:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="menu_snapshot")
        ]])
    )
    await state.set_state(AddBackupServer.entering_name)

@router.message(AddBackupServer.entering_name)
async def process_snapshot_name(message: Message, state: FSMContext):
    """Обработка названия резервного сервера"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(name=message.text)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление резервного сервера\n\n✅ Название: {message.text}\n\nВведите host (IP или домен):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="snapshot_add_server")
        ]])
    )
    await state.set_state(AddBackupServer.entering_host)

@router.message(AddBackupServer.entering_host)
async def process_snapshot_host(message: Message, state: FSMContext):
    """Обработка host резервного сервера"""
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
        text=f"➕ Добавление резервного сервера\n\n✅ Название: {data['name']}\n✅ Host: {message.text}\n\nВведите порт (по умолчанию 22):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="snapshot_add_server")
        ]])
    )
    await state.set_state(AddBackupServer.entering_port)

@router.message(AddBackupServer.entering_port)
async def process_snapshot_port(message: Message, state: FSMContext):
    """Обработка порта резервного сервера"""
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
            text=f"➕ Добавление резервного сервера\n\n✅ Название: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {port}\n\nВведите имя пользователя:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="snapshot_add_server")
            ]])
        )
        await state.set_state(AddBackupServer.entering_username)
    except ValueError:
        await message.answer("❌ Порт должен быть числом. Попробуйте еще раз:")

@router.message(AddBackupServer.entering_username)
async def process_snapshot_username(message: Message, state: FSMContext):
    """Обработка имени пользователя резервного сервера"""
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
        text=f"➕ Добавление резервного сервера\n\n✅ Название: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ Пользователь: {message.text}\n\nВведите пароль:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="snapshot_add_server")
        ]])
    )
    await state.set_state(AddBackupServer.entering_password)

@router.message(AddBackupServer.entering_password)
async def process_snapshot_password(message: Message, state: FSMContext):
    """Обработка пароля резервного сервера"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(password=message.text)
    data = await state.get_data()
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=f"➕ Добавление резервного сервера\n\n✅ Название: {data['name']}\n✅ Host: {data['host']}\n✅ Порт: {data['port']}\n✅ Пользователь: {data['username']}\n✅ Пароль: {'*' * len(data['password'])}\n\nВведите путь для сохранения бэкапов на сервере:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔙 Назад", callback_data="snapshot_add_server")
        ]])
    )
    await state.set_state(AddBackupServer.entering_remote_path)

@router.message(AddBackupServer.entering_remote_path)
async def process_snapshot_remote_path(message: Message, state: FSMContext):
    """Обработка пути для сохранения бэкапов"""
    data = await state.get_data()
    bot_message_id = data.get('bot_message_id')
    
    try:
        await message.delete()
    except:
        pass
    
    await state.update_data(remote_path=message.text)
    data = await state.get_data()
    
    text = "📋 Проверьте данные резервного сервера:\n\n"
    text += f"Название: {data['name']}\n"
    text += f"Host: {data['host']}\n"
    text += f"Порт: {data['port']}\n"
    text += f"Пользователь: {data['username']}\n"
    text += f"Пароль: {'*' * len(data['password'])}\n"
    text += f"Путь: {data['remote_path']}\n\n"
    text += "Сохранить сервер?"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Сохранить", callback_data="snapshot_confirm_save")
    keyboard.button(text="🔗 Проверить подключение", callback_data="snapshot_test_connection")
    keyboard.button(text="✏️ Редактировать", callback_data="snapshot_edit_before_save")
    keyboard.button(text="🔙 Назад", callback_data="snapshot_add_server")
    keyboard.adjust(1)
    
    await message.bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=bot_message_id,
        text=text,
        reply_markup=keyboard.as_markup()
    )
    await state.set_state(AddBackupServer.confirmation)

@router.callback_query(AddBackupServer.confirmation, F.data == "snapshot_test_connection")
async def snapshot_test_connection(callback_query: CallbackQuery, state: FSMContext):
    """Тестирование подключения к резервному серверу"""
    data = await state.get_data()
    
    await callback_query.message.edit_text("🔍 Проверяю подключение к резервному серверу...")
    
    success, message = await backup_transfer.connect(
        server_id=0,  # временный ID для теста
        host=data['host'],
        port=data['port'],
        username=data['username'],
        password=data['password']
    )
    
    # Закрываем тестовое соединение
    if success:
        await backup_transfer.close_connection(0)
    
    text = f"{message}\n\nСохранить сервер?"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Сохранить", callback_data="snapshot_confirm_save")
    keyboard.button(text="✏️ Редактировать", callback_data="snapshot_edit_before_save")
    keyboard.button(text="🔙 Назад", callback_data="snapshot_back_to_confirmation")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(AddBackupServer.confirmation, F.data == "snapshot_confirm_save")
async def snapshot_confirm_save(callback_query: CallbackQuery, state: FSMContext):
    """Сохранение резервного сервера"""
    data = await state.get_data()
    
    try:
        server_id = await add_backup_server(
            name=data['name'],
            host=data['host'],
            port=data['port'],
            username=data['username'],
            password=data['password'],
            remote_path=data['remote_path']
        )
        
        await callback_query.message.edit_text(
            f"✅ Резервный сервер '{data['name']}' успешно добавлен (ID: {server_id})",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📦 Управление снапшотами", callback_data="menu_snapshot"),
                InlineKeyboardButton(text="➕ Добавить еще", callback_data="snapshot_add_server")
            ], [
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_main")
            ]])
        )
        
    except Exception as e:
        await callback_query.message.edit_text(
            f"❌ Ошибка при добавлении резервного сервера: {str(e)}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="snapshot_back_to_confirmation")
            ]])
        )
    
    await state.clear()

# Браузер файлов на резервном сервере
@router.callback_query(F.data == "snapshot_browser")
async def snapshot_browser(callback_query: CallbackQuery):
    """Просмотр файлов на резервном сервере"""
    enabled_server = await get_enabled_backup_server()
    
    if not enabled_server:
        await callback_query.answer("❌ Нет активного резервного сервера")
        return
    
    await callback_query.message.edit_text(f"📁 Подключаюсь к резервному серверу {enabled_server['name']}...")
    
    # Подключаемся к серверу
    success, message = await backup_transfer.connect(
        server_id=enabled_server['id'],
        host=enabled_server['host'],
        port=enabled_server['port'],
        username=enabled_server['username'],
        password=enabled_server['password']
    )
    
    if not success:
        await callback_query.message.edit_text(
            f"❌ Не удалось подключиться к резервному серверу:\n{message}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="menu_snapshot")
            ]])
        )
        return
    
    # Получаем список файлов
    success, files, message = await backup_transfer.list_backup_files(
        server_id=enabled_server['id'],
        remote_path=enabled_server['remote_path']
    )
    
    # Закрываем соединение
    await backup_transfer.close_connection(enabled_server['id'])
    
    if not success:
        await callback_query.message.edit_text(
            f"❌ Ошибка получения списка файлов:\n{message}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data="menu_snapshot")
            ]])
        )
        return
    
    if not files:
        text = f"📁 Резервный сервер: {enabled_server['name']}\n\n"
        text += "📭 Нет файлов бэкапов"
    else:
        text = f"📁 Резервный сервер: {enabled_server['name']}\n\n"
        text += f"📊 {message}\n\n"
        
        for i, file_path in enumerate(files[:10], 1):  # Показываем первые 10 файлов
            file_name = os.path.basename(file_path)
            text += f"{i}. {file_name}\n"
            text += f"   📍 {file_path}\n\n"
        
        if len(files) > 10:
            text += f"... и еще {len(files) - 10} файлов"
    
    keyboard = InlineKeyboardBuilder()
    
    if files:
        keyboard.button(text="📥 Скачать все", callback_data="snapshot_download_all")
        keyboard.button(text="🗑️ Очистить старые", callback_data="snapshot_cleanup")
    
    keyboard.button(text="🔄 Обновить", callback_data="snapshot_browser")
    keyboard.button(text="🔙 Назад", callback_data="menu_snapshot")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Управление конкретным резервным сервером
@router.callback_query(F.data.startswith("snapshot_server_"))
async def snapshot_server_detail(callback_query: CallbackQuery):
    """Детальная информация о резервном сервере"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_backup_server(server_id)
    if not server:
        await callback_query.answer("❌ Резервный сервер не найден")
        return
    
    # Проверяем пинг
    is_online = await ping_server(server['host'])
    ping_status = "🟢 Онлайн" if is_online else "🔴 Офлайн"
    
    text = f"📦 Резервный сервер: {server['name']}\n\n"
    text += f"📍 Host: {server['host']}\n"
    text += f"🔢 Port: {server['port']}\n"
    text += f"👤 User: {server['username']}\n"
    text += f"📁 Путь: {server['remote_path']}\n"
    text += f"📊 Статус: {ping_status}\n"
    text += f"🔧 Включен: {'✅ Да' if server['enabled'] else '❌ Нет'}\n\n"
    text += "Выберите действие:"
    
    keyboard = InlineKeyboardBuilder()
    
    # Основные действия
    if server['enabled']:
        keyboard.button(text="🔴 Выключить", callback_data=f"snapshot_toggle_{server_id}")
    else:
        keyboard.button(text="🟢 Включить", callback_data=f"snapshot_toggle_{server_id}")
    
    keyboard.button(text="✏️ Редактировать", callback_data=f"snapshot_edit_{server_id}")
    keyboard.button(text="🗑️ Удалить", callback_data=f"snapshot_delete_{server_id}")
    keyboard.button(text="🔙 Назад", callback_data="menu_snapshot")
    keyboard.adjust(1)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

# Включение/выключение резервного сервера
@router.callback_query(F.data.startswith("snapshot_toggle_"))
async def snapshot_toggle(callback_query: CallbackQuery):
    """Включение/выключение резервного сервера"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_backup_server(server_id)
    if not server:
        await callback_query.answer("❌ Резервный сервер не найден")
        return
    
    new_status = not server['enabled']
    await update_backup_server(server_id, {'enabled': new_status})
    
    status_text = "включен" if new_status else "выключен"
    await callback_query.answer(f"Резервный сервер {status_text}")
    
    # Возвращаемся к детальной информации
    await snapshot_server_detail(callback_query)

# Удаление резервного сервера
@router.callback_query(F.data.startswith("snapshot_delete_"))
async def snapshot_delete(callback_query: CallbackQuery):
    """Удаление резервного сервера"""
    try:
        server_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_backup_server(server_id)
    if not server:
        await callback_query.answer("❌ Резервный сервер не найден")
        return
    
    text = f"❌ Удаление резервного сервера\n\nВы уверены, что хотите удалить сервер?\n\nИмя: {server['name']}\nHost: {server['host']}\n\nЭто действие нельзя отменить!"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.button(text="✅ Да, удалить", callback_data=f"snapshot_confirm_delete_{server_id}")
    keyboard.button(text="❌ Нет, отмена", callback_data=f"snapshot_server_{server_id}")
    keyboard.adjust(2)
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data.startswith("snapshot_confirm_delete_"))
async def snapshot_confirm_delete(callback_query: CallbackQuery):
    """Подтверждение удаления резервного сервера"""
    try:
        server_id = int(callback_query.data.split("_")[3])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка формата данных")
        return
    
    server = await get_backup_server(server_id)
    if not server:
        await callback_query.answer("❌ Резервный сервер не найден")
        return
    
    success = await delete_backup_server(server_id)
    
    if success:
        await callback_query.message.edit_text(
            f"✅ Резервный сервер '{server['name']}' успешно удален",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="📦 Управление снапшотами", callback_data="menu_snapshot"),
                InlineKeyboardButton(text="🔙 В главное меню", callback_data="menu_main")
            ]])
        )
    else:
        await callback_query.message.edit_text(
            "❌ Ошибка при удалении сервера",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"snapshot_server_{server_id}")
            ]])
        )