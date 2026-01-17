"""
Обработчики для Stage 5 (До беби-лифа) - ежедневные практики с долгосрочными целями
"""
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import date

from utils import practices_manager
from utils.db import update_user_progress
from models import SessionLocal, User

logger = logging.getLogger(__name__)


def _get_stage5_daily_practice(day: int):
    """
    Получить практику дня для Stage 5

    Args:
        day: номер дня (1-7)

    Returns:
        dict с практикой или None
    """
    stage = practices_manager.get_stage(5)
    if not stage:
        return None

    daily_practices = stage.get('daily_practices', [])
    for practice in daily_practices:
        if practice.get('day') == day:
            return practice

    return None


def _get_stage5_step_by_type(practice, step_type: str):
    """
    Получить подшаг практики по типу (question, feeling, affirmation)

    Args:
        practice: объект практики дня
        step_type: тип подшага

    Returns:
        dict с подшагом или None
    """
    steps = practice.get('steps', [])
    for step in steps:
        if step.get('type') == step_type:
            return step

    return None


async def handle_stage5_start_substep(query, user, db):
    """
    Начать подшаги Stage 5 (переход от напоминания к первому подшагу - intro)
    """
    current_day = user.daily_practice_day

    logger.info(f"Пользователь {user.telegram_id} начинает подшаги Stage 5, день {current_day}")

    # Получить практику текущего дня
    practice = _get_stage5_daily_practice(current_day)

    if not practice:
        logger.error(f"Практика дня {current_day} не найдена для Stage 5")
        await query.edit_message_text("Ошибка: практика дня не найдена")
        return

    # Установить текущий подшаг = "intro"
    user.daily_practice_substep = "intro"
    db.commit()

    # Получить первый подшаг (intro)
    step = _get_stage5_step_by_type(practice, "intro")

    if not step:
        logger.error(f"Подшаг 'intro' не найден для дня {current_day}")
        await query.edit_message_text("Ошибка: подшаг не найден")
        return

    # Сформировать сообщение
    theme = practice.get('theme', '')
    message = f"🌱 **День {current_day} из 7: {theme}**\n\n"
    message += step.get('text', '')

    # Кнопка "Продолжить"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Продолжить", callback_data="stage5_next_substep")]
    ])

    await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')

    logger.info(f"Пользователь {user.telegram_id} начал подшаг 'intro' дня {current_day} (Stage 5)")


async def handle_stage5_next_substep(query, user, db):
    """
    Переход к следующему подшагу Stage 5 (intro → timer → affirmation → watering → completion)
    """
    current_day = user.daily_practice_day
    current_substep = user.daily_practice_substep

    logger.info(f"Пользователь {user.telegram_id} переходит от подшага '{current_substep}' к следующему (Stage 5)")

    # Получить практику текущего дня
    practice = _get_stage5_daily_practice(current_day)

    if not practice:
        logger.error(f"Практика дня {current_day} не найдена для Stage 5")
        await query.edit_message_text("Ошибка: практика дня не найдена")
        return

    # Определить следующий подшаг
    next_substep = None
    if current_substep == "intro":
        next_substep = "timer"
    elif current_substep == "timer":
        next_substep = "affirmation"
    elif current_substep == "affirmation":
        next_substep = "watering"
    elif current_substep == "watering":
        # Это был последний подшаг - завершить день
        await _complete_stage5_day(query, user, db, practice)
        return

    if not next_substep:
        logger.error(f"Неизвестный подшаг '{current_substep}' для Stage 5")
        await query.edit_message_text("Ошибка: неизвестный подшаг")
        return

    # Обновить текущий подшаг
    user.daily_practice_substep = next_substep
    db.commit()

    # Получить следующий подшаг
    step = _get_stage5_step_by_type(practice, next_substep)

    if not step:
        logger.error(f"Подшаг '{next_substep}' не найден для дня {current_day}")
        await query.edit_message_text("Ошибка: подшаг не найден")
        return

    # Сформировать сообщение
    theme = practice.get('theme', '')
    message = f"🌱 **День {current_day} из 7: {theme}**\n\n"
    message += step.get('text', '')

    # Кнопка
    if next_substep == "timer":
        button_text = "Минута прошла"
    elif next_substep == "affirmation":
        button_text = "Принято. До завтра" if current_day < 7 else "Перейти к празднику зрелости"
    elif next_substep == "watering":
        button_text = "Ага"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(button_text, callback_data="stage5_next_substep")]
    ])

    await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')

    logger.info(f"Пользователь {user.telegram_id} перешёл к подшагу '{next_substep}' (Stage 5)")


async def _complete_stage5_day(query, user, db, practice):
    """
    Завершить день практики Stage 5

    Args:
        query: CallbackQuery
        user: User object
        db: Database session
        practice: практика дня
    """
    current_day = user.daily_practice_day

    logger.info(f"Пользователь {user.telegram_id} завершает день {current_day} (Stage 5)")

    # Проверить, был ли это последний день (день 7)
    if current_day >= 7:
        from datetime import timedelta

        # Переход к Stage 6 (Финал)
        update_user_progress(db, user.telegram_id, stage_id=6, step_id=24, day=user.current_day)

        # Установить напоминание на следующий день
        tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        user.stage6_reminder_date = tomorrow

        # Сбросить поля Stage 5
        user.daily_practice_day = 0
        user.daily_practice_substep = ""
        user.last_practice_date = None
        user.reminder_postponed = False
        user.postponed_until = None
        db.commit()

        await query.edit_message_text(
            "🎉 **Все 7 дней практик завершены!**\n\n"
            "Отличная работа! Ты освоил(а) навык работы с долгосрочными целями.\n\n"
            "Твой беби-лиф готов! Скоро мы перейдём к финальному этапу.\n\n"
            "🌱 Используй /status для продолжения.",
            parse_mode='Markdown'
        )

        logger.info(f"Пользователь {user.telegram_id} завершил Stage 5, переход к Stage 6")
        return

    # Обычное завершение дня
    user.daily_practice_day = current_day + 1
    user.daily_practice_substep = ""
    user.last_practice_date = date.today().strftime('%Y-%m-%d')
    user.reminder_postponed = False
    user.postponed_until = None
    db.commit()

    theme = practice.get('theme', '')
    await query.edit_message_text(
        f"✅ **День {current_day} завершён!**\n\n"
        f"Тема: {theme}\n\n"
        f"Молодец! Ты сделал(а) ещё один шаг в работе с долгосрочными целями.\n\n"
        f"🌱 До встречи завтра!",
        parse_mode='Markdown'
    )

    logger.info(f"Пользователь {user.telegram_id} завершил день {current_day} (Stage 5)")
