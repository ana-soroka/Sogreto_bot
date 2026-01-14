"""
Обработчики команд настроек:
/set_time - установка времени напоминаний
/timezone - установка часового пояса
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import error_handler
from utils.db import get_or_create_user
from models import SessionLocal
import pytz

logger = logging.getLogger(__name__)


@error_handler
async def set_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /set_time - установка времени напоминаний
    """
    user_id = update.effective_user.id

    # Создать клавиатуру с выбором времени
    keyboard = [
        [
            InlineKeyboardButton("09:00", callback_data="time_09:00"),
            InlineKeyboardButton("10:00", callback_data="time_10:00"),
            InlineKeyboardButton("11:00", callback_data="time_11:00"),
        ],
        [
            InlineKeyboardButton("12:00", callback_data="time_12:00"),
            InlineKeyboardButton("13:00", callback_data="time_13:00"),
            InlineKeyboardButton("14:00", callback_data="time_14:00"),
        ],
        [
            InlineKeyboardButton("15:00", callback_data="time_15:00"),
            InlineKeyboardButton("16:00", callback_data="time_16:00"),
            InlineKeyboardButton("17:00", callback_data="time_17:00"),
        ],
        [
            InlineKeyboardButton("18:00", callback_data="time_18:00"),
            InlineKeyboardButton("19:00", callback_data="time_19:00"),
            InlineKeyboardButton("20:00", callback_data="time_20:00"),
        ],
        [
            InlineKeyboardButton("21:00", callback_data="time_21:00"),
            InlineKeyboardButton("22:00", callback_data="time_22:00"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "⏰ **Настройка времени напоминаний**\n\n"
        "Выберите время, в которое вы хотите получать напоминания о практиках.\n\n"
        "Рекомендуем выбрать утреннее время (9:00-12:00) для лучшей концентрации.\n\n"
        "Напоминания будут приходить каждый день в выбранное время по вашему часовому поясу."
    )

    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user_id} открыл настройку времени напоминаний")


@error_handler
async def handle_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик выбора времени напоминаний
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    callback_data = query.data

    # Извлечь время из callback_data (формат: "time_HH:MM")
    if callback_data.startswith("time_"):
        time_str = callback_data.replace("time_", "")

        db = SessionLocal()
        try:
            user = get_or_create_user(
                db,
                telegram_id=user_id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name
            )

            # Сохранить время в БД
            user.preferred_time = time_str
            db.commit()

            await query.edit_message_text(
                f"✅ **Время напоминаний установлено!**\n\n"
                f"Вы будете получать напоминания о практиках каждый день в **{time_str}**.\n\n"
                f"Часовой пояс: {user.timezone}\n\n"
                f"Чтобы изменить время, используйте /set_time снова.\n"
                f"Чтобы изменить часовой пояс, используйте /timezone"
            )

            logger.info(f"Пользователь {user_id} установил время напоминаний: {time_str}")

        finally:
            db.close()


@error_handler
async def timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /timezone - установка часового пояса
    """
    user_id = update.effective_user.id

    # Популярные часовые пояса
    keyboard = [
        [
            InlineKeyboardButton("🇷🇺 Москва (UTC+3)", callback_data="tz_Europe/Moscow"),
        ],
        [
            InlineKeyboardButton("🇷🇺 Екатеринбург (UTC+5)", callback_data="tz_Asia/Yekaterinburg"),
        ],
        [
            InlineKeyboardButton("🇷🇺 Новосибирск (UTC+7)", callback_data="tz_Asia/Novosibirsk"),
        ],
        [
            InlineKeyboardButton("🇷🇺 Владивосток (UTC+10)", callback_data="tz_Asia/Vladivostok"),
        ],
        [
            InlineKeyboardButton("🇰🇿 Алматы (UTC+6)", callback_data="tz_Asia/Almaty"),
        ],
        [
            InlineKeyboardButton("🇺🇦 Киев (UTC+2)", callback_data="tz_Europe/Kiev"),
        ],
        [
            InlineKeyboardButton("🇧🇾 Минск (UTC+3)", callback_data="tz_Europe/Minsk"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message = (
        "🌍 **Настройка часового пояса**\n\n"
        "Выберите ваш часовой пояс для корректной отправки напоминаний.\n\n"
        "Это важно, чтобы практики приходили в удобное для вас время."
    )

    await update.message.reply_text(
        message,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user_id} открыл настройку часового пояса")


@error_handler
async def handle_timezone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик выбора часового пояса
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    callback_data = query.data

    # Извлечь timezone из callback_data (формат: "tz_Region/City")
    if callback_data.startswith("tz_"):
        timezone_str = callback_data.replace("tz_", "")

        db = SessionLocal()
        try:
            user = get_or_create_user(
                db,
                telegram_id=user_id,
                username=update.effective_user.username,
                first_name=update.effective_user.first_name,
                last_name=update.effective_user.last_name
            )

            # Сохранить timezone в БД
            user.timezone = timezone_str
            db.commit()

            # Получить текущее время в выбранном часовом поясе
            tz = pytz.timezone(timezone_str)
            from datetime import datetime
            current_time = datetime.now(tz).strftime("%H:%M")

            await query.edit_message_text(
                f"✅ **Часовой пояс установлен!**\n\n"
                f"Ваш часовой пояс: **{timezone_str}**\n"
                f"Текущее время: **{current_time}**\n\n"
                f"Теперь установите время напоминаний: /set_time"
            )

            logger.info(f"Пользователь {user_id} установил часовой пояс: {timezone_str}")

        finally:
            db.close()
