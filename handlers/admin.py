"""
Обработчики админских команд:
/reload_practices - перезагрузить practices.json
/admin_test - тестовое меню для админов
"""
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import error_handler, practices_manager

logger = logging.getLogger(__name__)

# ID администраторов
ADMIN_IDS = [
    1585940117,  # Ваш telegram_id
]


def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


@error_handler
async def reload_practices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reload_practices - перезагрузить practices.json"""
    user = update.effective_user

    # Проверка прав администратора
    if not is_admin(user.id):
        await update.message.reply_text(
            "⛔ У вас нет прав для выполнения этой команды."
        )
        logger.warning(f"Пользователь {user.id} ({user.username}) попытался выполнить /reload_practices без прав администратора")
        return

    try:
        # Перезагрузить practices.json
        practices_manager.load_practices()

        total_stages = practices_manager.get_total_stages()

        await update.message.reply_text(
            f"✅ **Практики перезагружены!**\n\n"
            f"📁 Файл: practices.json\n"
            f"📊 Загружено этапов: {total_stages}\n\n"
            f"Все новые тексты теперь будут отображаться пользователям."
        )

        logger.info(f"Администратор {user.id} ({user.username}) перезагрузил practices.json - загружено {total_stages} этапов")

    except FileNotFoundError:
        await update.message.reply_text(
            "❌ **Ошибка!**\n\n"
            "Файл practices.json не найден."
        )
        logger.error(f"Администратор {user.id} попытался перезагрузить practices.json, но файл не найден")

    except Exception as e:
        await update.message.reply_text(
            f"❌ **Ошибка при загрузке!**\n\n"
            f"Проверьте синтаксис JSON файла.\n\n"
            f"Ошибка: {str(e)}"
        )
        logger.error(f"Ошибка при перезагрузке practices.json: {e}")


@error_handler
async def admin_test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /admin_test - админское тестовое меню"""
    user = update.effective_user

    # Проверка прав администратора
    if not is_admin(user.id):
        await update.message.reply_text(
            "⛔ У вас нет прав для выполнения этой команды."
        )
        logger.warning(f"Пользователь {user.id} ({user.username}) попытался выполнить /admin_test без прав")
        return

    # Получить данные пользователя из БД
    from models import SessionLocal, User as UserModel
    db = SessionLocal()

    try:
        db_user = db.query(UserModel).filter(UserModel.telegram_id == user.id).first()

        if not db_user:
            await update.message.reply_text("❌ Пользователь не найден в БД. Используйте /start сначала.")
            return

        # Формируем сообщение с текущим состоянием
        status_text = (
            f"🛠 **Админское тестовое меню**\n\n"
            f"**Текущее состояние:**\n"
            f"• Этап: {db_user.current_stage}\n"
            f"• Шаг: {db_user.current_step}\n"
            f"• День: {db_user.current_day}\n"
            f"• Daily practice day: {db_user.daily_practice_day}\n"
            f"• Daily substep: {db_user.daily_practice_substep or '(нет)'}\n"
            f"• Stage 4 reminder: {db_user.stage4_reminder_date or '(не установлено)'}\n\n"
            f"**Выберите тест:**"
        )

        # Создаем кнопки для тестирования
        keyboard = [
            [InlineKeyboardButton("🧪 Тест: День 1 (Stage 3)", callback_data="admin_test_day1")],
            [InlineKeyboardButton("🧪 Тест: День 2 (Stage 3)", callback_data="admin_test_day2")],
            [InlineKeyboardButton("🧪 Тест: День 3 (Stage 3)", callback_data="admin_test_day3")],
            [InlineKeyboardButton("🧪 Тест: День 4 (Stage 3)", callback_data="admin_test_day4")],
            [InlineKeyboardButton("🧪 Тест: Якорь (Stage 4)", callback_data="admin_test_stage4")],
            [InlineKeyboardButton("🧪 Тест: День 1-7 (Stage 5)", callback_data="admin_test_stage5_menu")],
            [InlineKeyboardButton("📊 Обновить статус", callback_data="admin_refresh_status")],
        ]

        await update.message.reply_text(
            status_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

        logger.info(f"Администратор {user.id} открыл тестовое меню")

    finally:
        db.close()
