import os
import glob
import re
from aiogram import Router, F
from datetime import datetime
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from utils.db import get_connections, get_connection, update_connection_enabled
from utils.scheduler import perform_single_backup
from utils.db import log_backup

router = Router()

def is_admin(user_id: int) -> bool:
    admin_id = os.getenv('ADMIN_ID')
    if not admin_id:
        return False
    return user_id == int(admin_id)

def debug_callback(callback_data: str, handler_name: str):
    print(f"🔍 DEBUG [{handler_name}]: callback_data = '{callback_data}'")
    parts = callback_data.split('_')
    print(f"🔍 DEBUG: parts = {parts}, len = {len(parts)}")

def debug_callback_data(callback_query: CallbackQuery, handler_name: str):
    """Отладочная информация о callback_data"""
    print(f"🔍 DEBUG [{handler_name}]: callback_data = '{callback_query.data}'")
    parts = callback_query.data.split('_')
    print(f"🔍 DEBUG: parts = {parts}, len = {len(parts)}")

@router.callback_query(F.data == "debug_test")
async def debug_test_handler(callback_query: CallbackQuery):
    """Тестовый обработчик для отладки"""
    print(f"🔍 DEBUG TEST: callback_data = '{callback_query.data}'")
    await callback_query.answer("Тестовый обработчик сработал!")

@router.message(F.text == "🔄 Сделать бэкап сейчас")
async def manual_backup_start(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    connections = await get_connections()
    
    if not connections:
        await message.answer("📭 Нет сохраненных подключений")
        return
    
    keyboard = InlineKeyboardBuilder()
    for conn in connections:
        keyboard.button(
            text=f"{conn['name']} ({conn['db_type']})", 
            callback_data=f"backup_{conn['id']}"
        )
    keyboard.button(text="❌ Отмена", callback_data="cancel_backup")
    keyboard.adjust(1)
    
    await message.answer(
        "Выберите подключение для бэкапа:",
        reply_markup=keyboard.as_markup()
    )

@router.callback_query(F.data.startswith("backup_"))
async def perform_manual_backup(callback_query: CallbackQuery):
    try:
        connection_id = int(callback_query.data.split("_")[1])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка: неверный формат данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    await callback_query.message.edit_text(f"🔄 Выполняю бэкап {connection['name']}...")
    
    backup_dir = os.getenv('BACKUP_DIR', './backups')
    success, result = await perform_single_backup(connection, backup_dir)
    
    await log_backup(connection_id, success, result if not success else None)
    
    if success:
        await callback_query.message.edit_text(
            f"✅ Бэкап {connection['name']} успешно создан\n"
            f"Файл: {result}"
        )
    else:
        await callback_query.message.edit_text(
            f"❌ Ошибка бэкапа {connection['name']}:\n{result}"
        )

@router.message(F.text == "⚙️ Настройки автобэкапа")
async def backup_settings(message: Message):
    if not is_admin(message.from_user.id):
        return
    
    connections = await get_connections()
    
    if not connections:
        await message.answer("📭 Нет сохраненных подключений")
        return
    
    keyboard = InlineKeyboardBuilder()
    for conn in connections:
        status = "✅" if conn['enabled'] else "❌"
        keyboard.button(
            text=f"{status} {conn['name']}", 
            callback_data=f"autobackup_toggle_{conn['id']}"
        )
    keyboard.button(text="📋 Список подключений", callback_data="list_connections")
    keyboard.button(text="❌ Закрыть", callback_data="close")
    keyboard.adjust(1)
    
    text = "⚙️ Настройки автобэкапа:\n\n"
    text += "Нажмите на подключение чтобы включить/выключить автобэкап\n"
    text += "✅ - автобэкап включен\n❌ - автобэкап выключен"
    
    await message.answer(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data.startswith("autobackup_toggle_"))
async def toggle_autobackup(callback_query: CallbackQuery):
    try:
        connection_id = int(callback_query.data.split("_")[2])
    except (IndexError, ValueError):
        await callback_query.answer("❌ Ошибка: неверный формат данных")
        return
    
    connection = await get_connection(connection_id)
    if not connection:
        await callback_query.answer("❌ Подключение не найдено")
        return
    
    new_status = not connection['enabled']
    await update_connection_enabled(connection_id, new_status)
    
    status_text = "включен" if new_status else "выключен"
    await callback_query.answer(f"Автобэкап {status_text}")
    
    # Обновляем сообщение
    connections = await get_connections()
    keyboard = InlineKeyboardBuilder()
    for conn in connections:
        status = "✅" if conn['enabled'] else "❌"
        keyboard.button(
            text=f"{status} {conn['name']}", 
            callback_data=f"autobackup_toggle_{conn['id']}"
        )
    keyboard.button(text="📋 Список подключений", callback_data="list_connections")
    keyboard.button(text="❌ Закрыть", callback_data="close")
    keyboard.adjust(1)
    
    await callback_query.message.edit_reply_markup(reply_markup=keyboard.as_markup())

@router.callback_query(F.data == "list_connections")
async def show_connections_list(callback_query: CallbackQuery):
    connections = await get_connections()
    
    if not connections:
        await callback_query.message.edit_text("📭 Нет сохраненных подключений")
        return
    
    keyboard = InlineKeyboardBuilder()
    for conn in connections:
        keyboard.button(
            text=f"✏️ {conn['name']} ({conn['db_type']})", 
            callback_data=f"conn_edit_{conn['id']}"
        )
    keyboard.button(text="❌ Закрыть", callback_data="close")
    keyboard.adjust(1)
    
    text = "📊 Список подключений:\n\n"
    for conn in connections:
        status = "✅" if conn['enabled'] else "❌"
        text += f"{status} {conn['name']} ({conn['db_type']})\n"
        text += f"   ID: {conn['id']} | БД: {conn['database'] or conn['file_path']}\n\n"
    
    text += "Нажмите на подключение для редактирования или удаления"
    
    await callback_query.message.edit_text(text, reply_markup=keyboard.as_markup())

@router.callback_query(F.data == "cancel_backup")
async def cancel_backup(callback_query: CallbackQuery):
    await callback_query.message.edit_text("❌ Операция отменена")

@router.callback_query(F.data == "close")
async def close_message(callback_query: CallbackQuery):
    await callback_query.message.delete()

# Менеджер бэкапов
@router.callback_query(F.data == "menu_backup_manager")
async def menu_backup_manager(callback_query: CallbackQuery):
    """Главный вход в менеджер бэкапов"""
    try:
        await show_backup_files(callback_query.message, page=1)
        await callback_query.answer()
    except Exception as e:
        print(f"❌ ERROR in menu_backup_manager: {e}")
        await callback_query.answer("❌ Ошибка открытия менеджера")

async def show_backup_files(message: Message, page: int = 1):
    """Показать список файлов бэкапов с пагинацией"""
    backup_dir = os.getenv('BACKUP_DIR', './backups')

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir, exist_ok=True)
    
    # Получаем все файлы бэкапов (убираем дубликаты)
    all_files = set()
    for pattern in ['*.sql', '*.db', '*.bson', '*_*']:
        all_files.update(glob.glob(os.path.join(backup_dir, pattern)))
    
    # Преобразуем в список и фильтруем только файлы
    all_files = [f for f in all_files if os.path.isfile(f)]
    
    # Сортируем по времени изменения (новые сначала)
    all_files.sort(key=os.path.getmtime, reverse=True)
    
    # Убираем дубликаты по имени файла (на случай если есть одинаковые файлы в разных папках)
    unique_files = []
    seen_names = set()
    for file_path in all_files:
        file_name = os.path.basename(file_path)
        if file_name not in seen_names:
            seen_names.add(file_name)
            unique_files.append(file_path)
    
    all_files = unique_files
    
    if not all_files:
        try:
            keyboard = InlineKeyboardBuilder()
            keyboard.button(text="🔄 Сделать бэкап", callback_data="menu_backup")
            keyboard.button(text="🔙 Назад", callback_data="menu_main")
            keyboard.adjust(1)
            
            await message.edit_text(
                "📁 Менеджер бэкапов\n\n📭 Нет созданных бэкапов",
                reply_markup=keyboard.as_markup()
            )
        except Exception:
            pass
        return
    
    # Пагинация
    items_per_page = 10
    total_pages = max(1, (len(all_files) + items_per_page - 1) // items_per_page)
    
    # Корректируем номер страницы если он вне диапазона
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, len(all_files))
    page_files = all_files[start_idx:end_idx]
    
    text = f"📁 Менеджер бэкапов\n\n"
    text += f"Страница {page} из {total_pages}\n"
    text += f"Всего файлов: {len(all_files)}\n\n"
    
    for i, file_path in enumerate(page_files, start=1):
        file_name = os.path.basename(file_path)
        file_size = os.path.getsize(file_path)
        file_time = os.path.getmtime(file_path)
        time_str = datetime.fromtimestamp(file_time).strftime('%Y-%m-%d %H:%M:%S')
        
        text += f"{start_idx + i}. {file_name}\n"
        text += f"   📏 {file_size / 1024 / 1024:.2f} MB | 🕒 {time_str}\n\n"
    
    keyboard = InlineKeyboardBuilder()
    
    # Кнопки для скачивания файлов
    for i, file_path in enumerate(page_files, start=1):
        file_name = os.path.basename(file_path)
        keyboard.button(text=f"📥 {i}", callback_data=f"download_{file_name}")
    
    # Группируем кнопки файлов (по 2 в ряд)
    if page_files:
        keyboard.adjust(2)
    
    # Кнопки пагинации
    if total_pages > 1:
        pagination_buttons = []
        if page > 1:
            pagination_buttons.append(InlineKeyboardButton(
                text="◀️ Назад", 
                callback_data=f"page_{page-1}"
            ))
        
        pagination_buttons.append(InlineKeyboardButton(
            text=f"{page}/{total_pages}", 
            callback_data="noop"
        ))
        
        if page < total_pages:
            pagination_buttons.append(InlineKeyboardButton(
                text="Вперед ▶️", 
                callback_data=f"page_{page+1}"
            ))
        
        keyboard.row(*pagination_buttons)
    
    # Основные кнопки
    keyboard.button(text="🔄 Обновить", callback_data="menu_backup_manager")
    keyboard.button(text="🔙 Назад", callback_data="menu_main")
    keyboard.adjust(1)
    
    try:
        await message.edit_text(text, reply_markup=keyboard.as_markup())
    except Exception as e:
        if "message is not modified" not in str(e):
            print(f"Ошибка редактирования сообщения: {e}")
            
# Обработчики пагинации - ДОБАВЬТЕ ЭТИ ОБРАБОТЧИКИ
@router.callback_query(F.data.startswith("page_"))
async def backup_page_handler(callback_query: CallbackQuery):
    try:
        page = int(callback_query.data.split("_")[1])
        await show_backup_files(callback_query.message, page)
        await callback_query.answer()
    except (IndexError, ValueError) as e:
        print(f"Ошибка пагинации: {e}")
        await callback_query.answer("❌ Ошибка пагинации")

@router.callback_query(F.data.startswith("download_"))
async def download_backup(callback_query: CallbackQuery):
    """Скачивание файла бэкапа"""
    try:
        file_name = callback_query.data.split("_", 1)[1]
        backup_dir = os.getenv('BACKUP_DIR', './backups')
        file_path = os.path.join(backup_dir, file_name)
        
        if not os.path.exists(file_path):
            await callback_query.answer("❌ Файл не найден")
            return
        
        # Отправляем файл
        file = FSInputFile(file_path)
        await callback_query.message.answer_document(
            document=file,
            caption=f"📁 Бэкап: {file_name}"
        )
        
        await callback_query.answer("✅ Файл отправлен")
        
    except Exception as e:
        print(f"❌ ERROR in download_backup: {e}")
        await callback_query.answer(f"❌ Ошибка: {str(e)}")

@router.callback_query(F.data == "noop")
async def noop_handler(callback_query: CallbackQuery):
    await callback_query.answer()