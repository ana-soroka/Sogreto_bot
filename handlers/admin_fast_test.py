"""
Модуль для тестирования автоматической работы scheduler уведомлений

Команды (только для админов):
- /test_wait_scheduler <день> <время> - Установить день и ждать автоматической отправки от scheduler
- /test_status - Показать текущее состояние пользователя
- /test_reset - Сброс на День 1
"""

import logging
import pytz
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from models import SessionLocal, User
from utils.db import get_or_create_user
from handlers.decorators import error_handler

logger = logging.getLogger(__name__)

# Список админов (только они могут использовать тестовые команды)
ADMIN_IDS = [1585940117]


def is_admin(user_id: int) -> bool:
    """Проверка прав администратора"""
    return user_id in ADMIN_IDS


async def simulate_day_fast(db: Session, user: User, target_day: int) -> dict:
    """
    Установить пользователя на день N с правильным состоянием

    Args:
        db: БД сессия
        user: Пользователь
        target_day: День (1-20)

    Returns:
        dict: Информация о настроенном состоянии
    """
    # Установить started_at на N дней назад
    user.started_at = datetime.utcnow() - timedelta(days=target_day)

    # Сбросить last_reminder_sent чтобы напоминание отправилось
    user.last_reminder_sent = None

    # Настроить состояние в зависимости от дня
    if target_day == 1:
        user.current_stage = 1
        user.current_step = 1
        user.awaiting_sprouts = False
        state_info = {"stage": 1, "action": "Посадка"}

    elif 2 <= target_day <= 5:
        # Дни 2-5: Всходы (Stage 2)
        user.current_stage = 1
        user.current_step = 6
        user.awaiting_sprouts = True
        state_info = {"stage": 2, "action": f"Всходы день {target_day}"}

    elif 4 <= target_day <= 6:
        # Stage 3: Ежедневные практики (дни 1-4)
        user.current_stage = 3
        user.awaiting_sprouts = False
        practice_day = target_day - 3  # День 4 = practice_day 1
        user.daily_practice_day = max(0, min(practice_day, 4))
        state_info = {"stage": 3, "practice_day": user.daily_practice_day}

    elif target_day == 7:
        # День 7: Stage 4 (Якорь)
        user.current_stage = 4
        user.current_step = 12
        user.daily_practice_day = 0
        # Установить stage4_reminder_date на сегодня
        user_tz = pytz.timezone(user.timezone)
        today = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(user_tz).date()
        user.stage4_reminder_date = today.strftime('%Y-%m-%d')
        state_info = {"stage": 4, "action": "Якорь"}

    elif 8 <= target_day <= 14:
        # Stage 5: Ежедневные практики (дни 1-7)
        user.current_stage = 5
        practice_day = target_day - 7  # День 8 = practice_day 1
        user.daily_practice_day = min(practice_day, 7)
        state_info = {"stage": 5, "practice_day": user.daily_practice_day}

    elif target_day >= 14:
        # Stage 6: Финал
        user.current_stage = 6
        user.current_step = 24
        user.daily_practice_day = 0
        # Установить stage6_reminder_date на сегодня
        user_tz = pytz.timezone(user.timezone)
        today = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(user_tz).date()
        user.stage6_reminder_date = today.strftime('%Y-%m-%d')
        state_info = {"stage": 6, "action": "Финал"}

    else:
        state_info = {"stage": user.current_stage}

    db.commit()
    logger.info(f"TEST: Установлен день {target_day} для пользователя {user.telegram_id}, state_info={state_info}")
    return state_info


@error_handler
async def test_wait_scheduler_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /test_wait_scheduler <день> <время>
    Установить день и время, ждать автоматической отправки от scheduler
    """
    user = update.effective_user

    # Проверка прав администратора
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Недостаточно прав")
        return

    # Проверить аргументы
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Укажите день и время!\n\n"
            "Использование: /test_wait_scheduler <день> <время>\n"
            "Примеры:\n"
            "  /test_wait_scheduler 2 14:30\n"
            "  /test_wait_scheduler 5 09:00"
        )
        return

    try:
        target_day = int(context.args[0])
        time_str = context.args[1]

        # Валидация дня
        if target_day < 1 or target_day > 20:
            await update.message.reply_text("❌ День должен быть от 1 до 20")
            return

        # Валидация времени (HH:MM)
        try:
            hour, minute = map(int, time_str.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Некорректное время")
        except ValueError:
            await update.message.reply_text("❌ Время должно быть в формате HH:MM (например 09:00)")
            return

        # Получить пользователя из БД
        db = SessionLocal()
        try:
            db_user = db.query(User).filter(User.telegram_id == user.id).first()
            if not db_user:
                await update.message.reply_text("❌ Пользователь не найден. Используйте /start")
                return

            # Установить день (БЕЗ отправки напоминания)
            state_info = await simulate_day_fast(db, db_user, target_day)

            # Установить время напоминания
            db_user.preferred_time = time_str

            # Сбросить last_reminder_sent чтобы scheduler отправил
            db_user.last_reminder_sent = None

            db.commit()

            # Вычислить через сколько придёт напоминание
            user_tz = pytz.timezone(db_user.timezone)
            now_user_tz = datetime.utcnow().replace(tzinfo=pytz.utc).astimezone(user_tz)

            target_time = now_user_tz.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target_time < now_user_tz:
                # Если время уже прошло, добавить день
                target_time += timedelta(days=1)

            delta = target_time - now_user_tz
            minutes_left = int(delta.total_seconds() / 60)

            status_msg = (
                f"✅ **Установлен День {target_day}**\n\n"
                f"• Stage: {db_user.current_stage}\n"
                f"• Step: {db_user.current_step}\n"
            )

            if "practice_day" in state_info:
                status_msg += f"• Daily practice day: {state_info['practice_day']}\n"
            if "action" in state_info:
                status_msg += f"• Действие: {state_info['action']}\n"

            status_msg += (
                f"• Preferred time: {time_str}\n"
                f"• Timezone: {db_user.timezone}\n\n"
                f"⏰ **Ожидание автоматической отправки от scheduler**\n\n"
                f"Напоминание должно прийти в **{time_str}** (через ~{minutes_left} мин)\n\n"
                f"💡 Это проверяет что scheduler инициализировался после деплоя."
            )

            await update.message.reply_text(status_msg, parse_mode='Markdown')

        finally:
            db.close()

    except ValueError as e:
        await update.message.reply_text(f"❌ Некорректный формат: {str(e)}")
    except Exception as e:
        logger.error(f"Ошибка в /test_wait_scheduler: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)}")


@error_handler
async def test_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показать текущее состояние тестирования
    """
    user = update.effective_user

    # Проверка прав администратора
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Недостаточно прав")
        return

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.telegram_id == user.id).first()
        if not db_user:
            await update.message.reply_text("❌ Пользователь не найден. Используйте /start")
            return

        # Рассчитать день
        days_since = 0
        if db_user.started_at:
            days_since = (datetime.utcnow() - db_user.started_at).days

        status_text = (
            f"📊 **Статус тестирования**\n\n"
            f"**Время:**\n"
            f"• Started at: {db_user.started_at}\n"
            f"• Дней с начала: {days_since}\n"
            f"• Last reminder: {db_user.last_reminder_sent}\n\n"
            f"**Состояние:**\n"
            f"• Stage: {db_user.current_stage}\n"
            f"• Step: {db_user.current_step}\n"
            f"• Current day: {db_user.current_day}\n"
            f"• Daily practice day: {db_user.daily_practice_day}\n"
            f"• Daily substep: {db_user.daily_practice_substep or '(нет)'}\n\n"
            f"**Флаги:**\n"
            f"• awaiting_sprouts: {db_user.awaiting_sprouts}\n"
            f"• is_paused: {db_user.is_paused}\n"
            f"• Stage 4 reminder: {db_user.stage4_reminder_date or '(нет)'}\n"
            f"• Stage 6 reminder: {db_user.stage6_reminder_date or '(нет)'}\n\n"
            f"**Настройки:**\n"
            f"• Timezone: {db_user.timezone}\n"
            f"• Preferred time: {db_user.preferred_time or '(не установлено)'}"
        )

        await update.message.reply_text(status_text, parse_mode='Markdown')

    finally:
        db.close()


@error_handler
async def test_reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Сброс на День 1
    """
    user = update.effective_user

    # Проверка прав администратора
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Недостаточно прав")
        return

    db = SessionLocal()
    try:
        db_user = db.query(User).filter(User.telegram_id == user.id).first()
        if not db_user:
            await update.message.reply_text("❌ Пользователь не найден. Используйте /start")
            return

        # Сброс всех тестовых полей
        db_user.started_at = None
        db_user.last_reminder_sent = None
        db_user.current_stage = 1
        db_user.current_step = 1
        db_user.current_day = 1
        db_user.daily_practice_day = 0
        db_user.daily_practice_substep = ""
        db_user.awaiting_sprouts = False
        db_user.stage4_reminder_date = None
        db_user.stage6_reminder_date = None
        db_user.last_practice_date = None
        db_user.reminder_postponed = False
        db_user.postponed_until = None

        db.commit()

        await update.message.reply_text(
            "✅ **Сброс выполнен!**\n\n"
            "Все поля сброшены на начальное состояние:\n"
            "• started_at = None\n"
            "• last_reminder_sent = None\n"
            "• current_stage = 1\n"
            "• current_step = 1\n"
            "• daily_practice_day = 0\n"
            "• awaiting_sprouts = False",
            parse_mode='Markdown'
        )

        logger.info(f"TEST: Сброс состояния для пользователя {user.id}")

    finally:
        db.close()
