"""
Обработчики команд практик:
/start_practice и работа с практиками
"""
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import error_handler, practices_manager
from utils.db import get_or_create_user, update_user_progress
from models import SessionLocal, User
from handlers.admin import is_admin, ADMIN_IDS
from utils.scheduler import send_daily_practice_reminder
from handlers.practices_stage5 import handle_stage5_start_substep, handle_stage5_next_substep

logger = logging.getLogger(__name__)


def create_practice_keyboard(buttons_data):
    """
    Создать InlineKeyboard из данных кнопок практики

    Args:
        buttons_data: список словарей с keys 'text' и 'action'

    Returns:
        InlineKeyboardMarkup с кнопками
    """
    keyboard = []
    for button in buttons_data:
        callback_data = button.get('action', 'unknown')
        button_text = button.get('text', 'Продолжить')
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    return InlineKeyboardMarkup(keyboard)


@error_handler
async def start_practice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start_practice - начать практики"""
    user_id = update.effective_user.id

    db = SessionLocal()
    try:
        # Получить или создать пользователя
        user = get_or_create_user(
            db,
            telegram_id=user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name
        )

        # Проверить, не начаты ли уже практики
        if user.current_stage > 1 or user.current_step > 1:
            await update.message.reply_text(
                f"У вас уже есть активные практики!\n\n"
                f"📍 Этап: {user.current_stage}\n"
                f"📝 Шаг: {user.current_step}\n\n"
                f"Используйте /status чтобы увидеть прогресс.\n"
                f"Если хотите начать сначала, используйте /reset"
            )
            return

        # Получить первый шаг первого этапа (stage_id=1, step_id=1)
        first_step = practices_manager.get_step(stage_id=1, step_id=1)

        if not first_step:
            await update.message.reply_text(
                "😞 Извините, произошла ошибка при загрузке практик.\n"
                "Пожалуйста, попробуйте позже или свяжитесь с поддержкой: /contact"
            )
            logger.error(f"Не удалось загрузить первый шаг практики для пользователя {user_id}")
            return

        # Обновить прогресс пользователя
        update_user_progress(db, user_id, stage_id=1, step_id=1, day=1)

        # Установить started_at если это первый раз
        from datetime import datetime
        if not user.started_at:
            user.started_at = datetime.utcnow()
            db.commit()

        # Сформировать сообщение
        message = f"**{first_step.get('title', 'Начало практики')}**\n\n"
        message += first_step.get('message', '')

        # Создать клавиатуру с кнопками
        buttons = first_step.get('buttons', [])
        keyboard = create_practice_keyboard(buttons)

        # Отправить практику с кнопками
        await update.message.reply_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        logger.info(f"Пользователь {user_id} начал практики - отправлен шаг 1")

    finally:
        db.close()


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ МНОГОШАГОВЫХ ПРАКТИК ====================

def _get_daily_practice_by_day(stage, day):
    """Получить практику по номеру дня"""
    daily_practices = stage.get('daily_practices', [])
    for practice in daily_practices:
        if practice.get('day') == day:
            return practice
    return None


def _get_substep_by_id(daily_practice, substep_id):
    """Получить подшаг по substep_id"""
    substeps = daily_practice.get('substeps', [])
    for substep in substeps:
        if substep.get('substep_id') == substep_id:
            return substep
    return None


def _get_next_substep_id(current_substep_id):
    """Определить следующий подшаг"""
    flow = {
        "intro": "practice",
        "practice": "checkin",  # По умолчанию practice → checkin
        "practice2": "checkin",
        "response_A": "completion",
        "response_B": "completion"
    }
    return flow.get(current_substep_id, "completion")


async def _send_substep_message(query, substep):
    """Отправить сообщение подшага с кнопками"""
    title = substep.get('title', '')
    message = substep.get('message', '')

    if title:
        full_message = f"**{title}**\n\n{message}"
    else:
        full_message = message

    buttons = substep.get('buttons', [])
    keyboard = create_practice_keyboard(buttons) if buttons else None

    await query.edit_message_text(
        full_message,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


# ==================== ОБРАБОТЧИКИ МНОГОШАГОВЫХ ПРАКТИК ====================

async def handle_start_daily_substep(query, user, db):
    """
    Начать подшаги дня (переход от напоминания к первому подшагу)
    """
    current_day = user.daily_practice_day

    logger.info(f"Пользователь {user.telegram_id} начинает подшаги дня {current_day}")

    # Получить практику текущего дня
    stage = practices_manager.get_stage(3)
    if not stage:
        logger.error("Этап 3 не найден в practices.json")
        await query.edit_message_text("Ошибка: этап не найден")
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)

    if not daily_practice:
        logger.error(f"Практика дня {current_day} не найдена")
        await query.edit_message_text(f"Ошибка: практика дня {current_day} не найдена")
        return

    # Установить текущий подшаг = "intro"
    user.daily_practice_substep = "intro"
    db.commit()

    # Получить первый подшаг
    substep = _get_substep_by_id(daily_practice, "intro")

    if not substep:
        logger.error(f"Подшаг 'intro' не найден для дня {current_day}")
        await query.edit_message_text("Ошибка: подшаг не найден")
        return

    # Отправить сообщение подшага
    await _send_substep_message(query, substep)

    logger.info(f"Пользователь {user.telegram_id} начал подшаги дня {current_day}")


async def handle_next_daily_substep(query, user, db, context):
    """
    Переход к следующему подшагу
    """
    current_day = user.daily_practice_day
    current_substep = user.daily_practice_substep

    logger.info(f"Пользователь {user.telegram_id} переходит от подшага '{current_substep}' к следующему")

    # Получить практику текущего дня
    stage = practices_manager.get_stage(3)
    if not stage:
        logger.error("Этап 3 не найден в practices.json")
        await query.edit_message_text("Ошибка: этап не найден")
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)
    if not daily_practice:
        logger.error(f"Практика дня {current_day} не найдена")
        await query.edit_message_text(f"Ошибка: практика дня {current_day} не найдена")
        return

    # Определить следующий подшаг
    next_substep_id = _get_next_substep_id(current_substep)

    # Проверить, существует ли этот substep в практике
    substep = _get_substep_by_id(daily_practice, next_substep_id)

    # Если после practice идёт checkin, но есть practice2 - используем его
    if current_substep == "practice":
        practice2_substep = _get_substep_by_id(daily_practice, "practice2")
        if practice2_substep:
            next_substep_id = "practice2"
            substep = practice2_substep

    if not substep:
        logger.error(f"Подшаг '{next_substep_id}' не найден для дня {current_day}")
        await query.edit_message_text("Ошибка: подшаг не найден")
        return

    # Обновить текущий подшаг
    user.daily_practice_substep = next_substep_id
    db.commit()

    # Проверить авто-переходы
    if substep.get('auto_proceed'):
        await _send_substep_message(query, substep)
        await asyncio.sleep(3)
        await handle_next_daily_substep(query, user, db, context)
        return

    if substep.get('auto_complete'):
        await _complete_daily_practice_flow(query, user, db, substep)
        return

    # Отправить сообщение подшага
    await _send_substep_message(query, substep)

    logger.info(f"Пользователь {user.telegram_id} перешёл к подшагу {next_substep_id}")


async def handle_daily_choice_A(query, user, db, context):
    """Выбор кнопки A в check-in"""
    user.daily_practice_substep = "response_A"
    db.commit()
    await _send_response_substep(query, user, db, context, "response_A")


async def handle_daily_choice_B(query, user, db, context):
    """Выбор кнопки B в check-in"""
    user.daily_practice_substep = "response_B"
    db.commit()
    await _send_response_substep(query, user, db, context, "response_B")


async def _send_response_substep(query, user, db, context, substep_id):
    """
    Отправить ответный подшаг (response_A или response_B)
    Показать с кнопками из JSON
    """
    current_day = user.daily_practice_day
    stage = practices_manager.get_stage(3)
    if not stage:
        logger.error("Этап 3 не найден в practices.json")
        await query.edit_message_text("Ошибка: этап не найден")
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)
    if not daily_practice:
        logger.error(f"Практика дня {current_day} не найдена")
        await query.edit_message_text(f"Ошибка: практика дня {current_day} не найдена")
        return

    substep = _get_substep_by_id(daily_practice, substep_id)
    if not substep:
        logger.error(f"Подшаг '{substep_id}' не найден для дня {current_day}")
        await query.edit_message_text("Ошибка: подшаг не найден")
        return

    # Отправить сообщение с кнопками
    await _send_substep_message(query, substep)

    logger.info(f"Пользователь {user.telegram_id} получил response substep {substep_id}")


async def _complete_daily_practice_flow(query, user, db, final_substep):
    """
    Завершить флоу ежедневной практики
    """
    from datetime import date

    current_day = user.daily_practice_day

    # Отправить финальное сообщение
    message = final_substep.get('message', '')
    await query.edit_message_text(message, parse_mode='Markdown')

    # Проверить, был ли это последний день
    if current_day >= 4:
        # Переход к Stage 4
        from datetime import timedelta

        update_user_progress(db, user.telegram_id, stage_id=4, step_id=12, day=user.current_day)
        user.daily_practice_day = 0
        user.daily_practice_substep = ""
        user.last_practice_date = None
        user.reminder_postponed = False
        user.postponed_until = None

        # Установить напоминание о Stage 4 на завтра
        tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        user.stage4_reminder_date = tomorrow

        db.commit()

        logger.info(f"Пользователь {user.telegram_id} завершил все ежедневные практики, переход к этапу 4. Напоминание установлено на {tomorrow}")
        return

    # Обычное завершение дня
    user.daily_practice_day = current_day + 1
    user.daily_practice_substep = ""
    user.last_practice_date = date.today().strftime('%Y-%m-%d')
    user.reminder_postponed = False
    user.postponed_until = None
    db.commit()

    logger.info(f"Пользователь {user.telegram_id} завершил практику дня {current_day}")


async def handle_prev_daily_substep(query, user, db):
    """Вернуться к предыдущему подшагу ежедневной практики Stage 3"""

    current_substep = user.daily_practice_substep
    current_day = user.daily_practice_day

    # Карта переходов НАЗАД
    substep_back_flow = {
        "practice": "intro",
        "checkin": "practice",
        "response_A": "checkin",
        "response_B": "checkin",
    }

    prev_substep = substep_back_flow.get(current_substep)

    if not prev_substep:
        # Нельзя вернуться назад с intro или неизвестного подшага
        await query.answer("Это первый подшаг, вернуться назад нельзя.", show_alert=True)
        return

    # Обновить текущий подшаг
    user.daily_practice_substep = prev_substep
    db.commit()

    # Получить данные предыдущего подшага
    stage = practices_manager.get_stage(3)
    if not stage:
        logger.error("Этап 3 не найден в practices.json")
        await query.edit_message_text("Ошибка: этап не найден")
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)
    if not daily_practice:
        logger.error(f"Практика дня {current_day} не найдена")
        await query.edit_message_text(f"Ошибка: практика дня {current_day} не найдена")
        return

    prev_substep_data = _get_substep_by_id(daily_practice, prev_substep)
    if not prev_substep_data:
        logger.error(f"Подшаг '{prev_substep}' не найден для дня {current_day}")
        await query.answer("Ошибка: подшаг не найден", show_alert=True)
        return

    # Отправить сообщение предыдущего подшага с кнопками
    await _send_substep_message(query, prev_substep_data)

    logger.info(f"Пользователь {user.telegram_id} вернулся к подшагу '{prev_substep}' (день {current_day})")


@error_handler
async def handle_practice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик нажатий на кнопки практик (callback_query)
    """
    query = update.callback_query
    await query.answer()  # Подтвердить нажатие кнопки

    user_id = update.effective_user.id
    action = query.data  # Получить action из callback_data

    logger.info(f"Пользователь {user_id} нажал кнопку: {action}")

    db = SessionLocal()
    try:
        user = get_or_create_user(
            db,
            telegram_id=user_id,
            username=update.effective_user.username,
            first_name=update.effective_user.first_name,
            last_name=update.effective_user.last_name
        )

        # Обработать разные действия
        if action == "next_step":
            await handle_next_step(query, user, db)
        elif action == "prev_step":
            await handle_prev_step(query, user, db)
        elif action == "complete_stage":
            await handle_complete_stage(query, user, db)
        elif action == "show_examples_menu":
            # Сбросить состояние при входе в меню
            context.user_data['opened_categories'] = set()
            await handle_show_examples(query, user, db)
        elif action.startswith("toggle_category_"):
            # Извлечь ID категории из callback_data
            category_id = action.replace("toggle_category_", "")
            # Получить или создать set открытых категорий
            if 'opened_categories' not in context.user_data:
                context.user_data['opened_categories'] = set()
            opened_categories = context.user_data['opened_categories']
            await handle_category_toggle(query, user, db, category_id, opened_categories)
        elif action == "continue_from_examples":
            # Очистить состояние и вернуться к практике
            context.user_data.pop('opened_categories', None)
            await handle_next_step(query, user, db)
        elif action == "show_recipes":
            # Сбросить состояние при входе в меню рецептов
            context.user_data['opened_recipes'] = set()
            await handle_show_recipes(query, user, db, context)
        elif action.startswith("expand_recipe_") or action.startswith("collapse_recipe_"):
            # Извлечь ID рецепта из callback_data
            recipe_id = action.replace("expand_recipe_", "").replace("collapse_recipe_", "")
            # Получить или создать set открытых рецептов
            if 'opened_recipes' not in context.user_data:
                context.user_data['opened_recipes'] = set()
            opened_recipes = context.user_data['opened_recipes']
            await handle_recipe_toggle(query, user, db, recipe_id, opened_recipes, context)
        elif action == "start_waiting_for_daily":
            await handle_start_waiting_for_daily(query, user, db)
        elif action == "complete_daily_practice":
            await handle_complete_daily_practice(query, user, db)
        elif action == "postpone_reminder":
            await handle_postpone_reminder(query, user, db)
        elif action == "view_daily_practice":
            await handle_view_daily_practice(query, user, db)
        elif action == "show_manifesto":
            await handle_show_manifesto(query, user, db)
        elif action == "start_daily_practices":
            await handle_start_daily_practices(query, user, db)
        elif action == "sprouts_appeared":
            await handle_sprouts_appeared(query, user, db)
        elif action == "continue_practice":
            await handle_continue_practice(query, user, db)
        elif action == "confirm_reset":
            await handle_confirm_reset(query, user, db)
        elif action == "cancel_reset":
            await handle_cancel_reset(query, user, db)
        elif action == "start_practice_after_reset":
            await handle_start_practice_after_reset(query, user, db)
        elif action == "test_daily_reminder":
            await handle_test_daily_reminder(query, user, db, context)
        elif action == "start_daily_substep":
            await handle_start_daily_substep(query, user, db)
        elif action == "next_daily_substep":
            await handle_next_daily_substep(query, user, db, context)
        elif action == "prev_daily_substep":
            await handle_prev_daily_substep(query, user, db)
        elif action == "daily_choice_A":
            await handle_daily_choice_A(query, user, db, context)
        elif action == "daily_choice_B":
            await handle_daily_choice_B(query, user, db, context)
        elif action == "complete_day4_practice":
            await handle_complete_day4_practice(query, user, db, context)
        elif action == "test_stage4_reminder":
            await handle_test_stage4_reminder(query, user, db, context)
        elif action == "stage5_start_substep":
            await handle_stage5_start_substep(query, user, db)
        elif action == "stage5_next_substep":
            await handle_stage5_next_substep(query, user, db)
        elif action == "start_stage6_finale":
            await handle_start_stage6_finale(query, user, db)
        elif action.startswith("stage1_tz_"):
            await handle_stage1_timezone(query, user, db, action)
        elif action.startswith("stage1_time_"):
            await handle_stage1_time(query, user, db, action)
        elif action == "replant_start":
            await handle_replant_start(query, user, db)
        elif action.startswith("replant_step_"):
            step_id = int(action.split("_")[-1])
            await handle_replant_step(query, user, db, step_id)
        elif action == "replant_complete":
            await handle_replant_complete(query, user, db)
        elif action == "mold_start":
            await handle_mold_start(query, user, db)
        elif action == "mold_complete":
            await handle_mold_complete(query, user, db)
        elif action == "mold_sprouts_start":
            await handle_mold_sprouts_start(query, user, db)
        elif action == "mold_sprouts_complete":
            await handle_mold_sprouts_complete(query, user, db)
        else:
            await query.edit_message_text(
                f"Действие '{action}' пока не реализовано.\n"
                f"Скоро будет добавлено! 🌱"
            )
            logger.warning(f"Неизвестное действие: {action}")

    finally:
        db.close()


async def handle_next_step(query, user, db):
    """Перейти к следующему шагу практики"""
    current_stage = user.current_stage
    current_step = user.current_step

    # Получить текущий этап
    stage = practices_manager.get_stage(current_stage)
    if not stage:
        await query.edit_message_text("Ошибка: этап не найден")
        return

    steps = stage.get('steps', [])

    # Найти следующий шаг
    next_step_id = current_step + 1
    next_step = None
    for step in steps:
        if step.get('step_id') == next_step_id:
            next_step = step
            break

    if next_step:
        # Обновить прогресс пользователя
        update_user_progress(db, user.telegram_id, stage_id=current_stage, step_id=next_step_id, day=user.current_day)

        # Сформировать сообщение
        message = f"**{next_step.get('title', 'Практика')}**\n\n"
        message += next_step.get('message', '')

        # Создать клавиатуру
        buttons = next_step.get('buttons', [])
        keyboard = create_practice_keyboard(buttons)

        # Отправить следующий шаг
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        logger.info(f"Пользователь {user.telegram_id} перешел на шаг {next_step_id} этапа {current_stage}")
    else:
        # Шагов больше нет в текущем этапе
        await query.edit_message_text(
            f"Этап {current_stage} завершен! 🎉\n\n"
            f"Следующий этап будет доступен позже.\n"
            f"Используйте /status чтобы увидеть прогресс."
        )


async def handle_prev_step(query, user, db):
    """Вернуться к предыдущему шагу практики"""
    current_stage = user.current_stage
    current_step = user.current_step

    # Нельзя вернуться назад с первого шага
    if current_step <= 1:
        await query.answer("Это первый шаг, вернуться назад нельзя.", show_alert=True)
        return

    # Получить текущий этап
    stage = practices_manager.get_stage(current_stage)
    if not stage:
        await query.edit_message_text("Ошибка: этап не найден")
        return

    steps = stage.get('steps', [])

    # Найти предыдущий шаг
    prev_step_id = current_step - 1
    prev_step = None
    for step in steps:
        if step.get('step_id') == prev_step_id:
            prev_step = step
            break

    if prev_step:
        # Обновить прогресс пользователя
        update_user_progress(db, user.telegram_id, stage_id=current_stage, step_id=prev_step_id, day=user.current_day)

        # Сформировать сообщение
        message = f"**{prev_step.get('title', 'Практика')}**\n\n"
        message += prev_step.get('message', '')

        # Создать клавиатуру
        buttons = prev_step.get('buttons', [])
        keyboard = create_practice_keyboard(buttons)

        # Отправить предыдущий шаг
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        logger.info(f"Пользователь {user.telegram_id} вернулся на шаг {prev_step_id} этапа {current_stage}")
    else:
        await query.edit_message_text("Ошибка: предыдущий шаг не найден")


async def handle_complete_stage(query, user, db):
    """Завершить текущий этап и перейти к следующему"""
    current_stage = user.current_stage

    # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ЭТАПА 1: сначала настройка часового пояса и времени
    if current_stage == 1:
        # Установить флаг ожидания всходов
        user.awaiting_sprouts = True
        db.commit()

        # Сначала показать выбор часового пояса
        keyboard = [
            [InlineKeyboardButton("🇷🇺 Москва (UTC+3)", callback_data="stage1_tz_Europe/Moscow")],
            [InlineKeyboardButton("🇷🇺 Екатеринбург (UTC+5)", callback_data="stage1_tz_Asia/Yekaterinburg")],
            [InlineKeyboardButton("🇷🇺 Новосибирск (UTC+7)", callback_data="stage1_tz_Asia/Novosibirsk")],
            [InlineKeyboardButton("🇷🇺 Владивосток (UTC+10)", callback_data="stage1_tz_Asia/Vladivostok")],
            [InlineKeyboardButton("🇰🇿 Алматы (UTC+6)", callback_data="stage1_tz_Asia/Almaty")],
            [InlineKeyboardButton("🇧🇾 Минск (UTC+3)", callback_data="stage1_tz_Europe/Minsk")],
        ]

        await query.edit_message_text(
            f"🌍 **Настройка часового пояса**\n\n"
            f"Прежде чем продолжить, давай настроим напоминания!\n\n"
            f"Выбери свой часовой пояс, чтобы напоминания приходили вовремя:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        logger.info(f"Пользователь {user.telegram_id} завершил этап 1, выбирает часовой пояс")
        return

    # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ЭТАПА 2: переход к ежедневным практикам этапа 3
    if current_stage == 2:
        # Перейти на этап 3, шаг 0 (переходное сообщение)
        update_user_progress(db, user.telegram_id, stage_id=3, step_id=0, day=user.current_day)

        # Получить переходное сообщение (step_id=0) из этапа 3
        stage = practices_manager.get_stage(3)
        if stage:
            steps = stage.get('steps', [])
            transition_step = None
            for step in steps:
                if step.get('step_id') == 0:
                    transition_step = step
                    break

            if transition_step:
                message = f"**{transition_step.get('title', 'Переход')}**\n\n"
                message += transition_step.get('message', '')

                buttons = transition_step.get('buttons', [])
                # Создать клавиатуру с возможностью добавления админской кнопки
                keyboard_buttons = []
                for button in buttons:
                    text = button.get('text', '')
                    action = button.get('action', '')
                    if text and action:
                        keyboard_buttons.append([InlineKeyboardButton(text, callback_data=action)])

                # Добавить админскую кнопку если пользователь - админ
                if is_admin(user.telegram_id):
                    keyboard_buttons.append([InlineKeyboardButton("🧪 Тест-напоминание", callback_data="test_daily_reminder")])

                keyboard = InlineKeyboardMarkup(keyboard_buttons)

                await query.edit_message_text(
                    message,
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                logger.info(f"Пользователь {user.telegram_id} завершил этап 2, переход к ежедневным практикам")
                return

        # Fallback если не нашли переходный шаг
        await query.edit_message_text("Ошибка: переходное сообщение этапа 3 не найдено")
        return

    # Перейти к следующему этапу
    next_stage = current_stage + 1

    # Проверить, существует ли следующий этап
    stage = practices_manager.get_stage(next_stage)

    if stage:
        # Обновить прогресс: новый этап, первый шаг
        update_user_progress(db, user.telegram_id, stage_id=next_stage, step_id=1, day=user.current_day)

        await query.edit_message_text(
            f"🎉 Этап {current_stage} завершён!\n\n"
            f"Переходим к этапу {next_stage}: **{stage.get('stage_name', 'Следующий этап')}**\n\n"
            f"Следующая практика придёт позже (автоматические напоминания будут реализованы на следующем этапе).\n\n"
            f"Используйте /status чтобы увидеть прогресс."
        )
        logger.info(f"Пользователь {user.telegram_id} завершил этап {current_stage}, переход на этап {next_stage}")
    else:
        # Практики закончились
        await query.edit_message_text(
            f"🎊 **ПОЗДРАВЛЯЕМ!** 🎊\n\n"
            f"Вы завершили все практики предвкушения!\n\n"
            f"Вы прошли путь от семечка до урожая. 🌱\n\n"
            f"Используйте /status чтобы увидеть итоги."
        )
        logger.info(f"Пользователь {user.telegram_id} завершил ВСЕ практики!")


async def handle_stage1_timezone(query, user, db, action):
    """Обработать выбор часового пояса после завершения этапа 1"""
    # Извлечь timezone из action (формат: "stage1_tz_Region/City")
    timezone_str = action.replace("stage1_tz_", "")

    # Сохранить timezone в БД
    user.timezone = timezone_str
    db.commit()

    logger.info(f"Пользователь {user.telegram_id} выбрал часовой пояс: {timezone_str}")

    # Показать выбор времени напоминаний
    keyboard = [
        [
            InlineKeyboardButton("09:00", callback_data="stage1_time_09:00"),
            InlineKeyboardButton("10:00", callback_data="stage1_time_10:00"),
            InlineKeyboardButton("11:00", callback_data="stage1_time_11:00"),
        ],
        [
            InlineKeyboardButton("12:00", callback_data="stage1_time_12:00"),
            InlineKeyboardButton("13:00", callback_data="stage1_time_13:00"),
            InlineKeyboardButton("14:00", callback_data="stage1_time_14:00"),
        ],
        [
            InlineKeyboardButton("18:00", callback_data="stage1_time_18:00"),
            InlineKeyboardButton("19:00", callback_data="stage1_time_19:00"),
            InlineKeyboardButton("20:00", callback_data="stage1_time_20:00"),
        ],
        [
            InlineKeyboardButton("21:00", callback_data="stage1_time_21:00"),
            InlineKeyboardButton("22:00", callback_data="stage1_time_22:00"),
        ],
    ]

    await query.edit_message_text(
        f"⏰ **Настройка времени напоминаний**\n\n"
        f"Часовой пояс: **{timezone_str}** ✓\n\n"
        f"Теперь выбери время, в которое тебе удобно получать напоминания о проверке всходов:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_stage1_time(query, user, db, action):
    """Обработать выбор времени напоминаний после завершения этапа 1"""
    # Извлечь время из action (формат: "stage1_time_HH:MM")
    time_str = action.replace("stage1_time_", "")

    # Сохранить время в БД
    user.preferred_time = time_str
    db.commit()

    logger.info(f"Пользователь {user.telegram_id} выбрал время напоминаний: {time_str}")

    # Показать финальное сообщение о завершении этапа 1
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌱 Появились первые всходы!", callback_data="sprouts_appeared")]
    ])

    await query.edit_message_text(
        f"🎉 **Этап 1 завершён!**\n\n"
        f"Отличная работа! Семена посажены, и теперь начинается самое волнующее — ожидание.\n\n"
        f"⏰ Напоминания настроены: **{time_str}** ({user.timezone})\n\n"
        f"Обычно первые всходы появляются через **2-4 дня**.\n\n"
        f"💡 **Что делать:**\n"
        f"• Проверяй горшок каждый день\n"
        f"• Следи за влажностью почвы\n"
        f"• Держи горшок под плёнкой\n\n"
        f"Как только увидишь первые зелёные петельки — нажми кнопку ниже, и мы продолжим! 🌱\n\n"
        f"_Я буду присылать напоминания проверить всходы._",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )


async def handle_sprouts_appeared(query, user, db):
    """Обработать нажатие кнопки 'Появились первые всходы'"""
    # Сбросить флаг ожидания всходов
    user.awaiting_sprouts = False

    # Перейти на этап 2
    update_user_progress(db, user.telegram_id, stage_id=2, step_id=1, day=user.current_day)

    # Получить первый шаг этапа 2
    stage = practices_manager.get_stage(2)
    if not stage:
        await query.edit_message_text("Ошибка: этап 2 не найден")
        return

    steps = stage.get('steps', [])
    first_step = None
    for step in steps:
        if step.get('step_id') == 1:
            first_step = step
            break

    if first_step:
        # Сформировать сообщение
        message = f"**{first_step.get('title', 'Практика')}**\n\n"
        message += first_step.get('message', '')

        # Создать клавиатуру
        buttons = first_step.get('buttons', [])
        keyboard = create_practice_keyboard(buttons)

        # Отправить первый шаг
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        logger.info(f"Пользователь {user.telegram_id} сообщил о всходах, переход на этап 2")
    else:
        await query.edit_message_text("Ошибка: первый шаг этапа 2 не найден")


async def handle_show_examples(query, user, db, opened_categories=None):
    """Показать примеры желаний с аккордеоном

    Args:
        opened_categories: set строк с id открытых категорий
    """
    if opened_categories is None:
        opened_categories = set()

    examples = practices_manager.get_examples_menu()

    message = f"**{examples.get('title', 'Примеры желаний')}**\n\n"
    message += examples.get('message', '') + "\n\n"

    categories = examples.get('categories', [])
    keyboard = []

    # Создаём кнопки для каждой категории
    for category in categories:
        cat_id = category.get('id', '')
        is_open = cat_id in opened_categories

        # Иконка стрелки: вниз если открыто, вправо если закрыто
        arrow = "🔽" if is_open else "▶️"
        button_text = f"{arrow} {category.get('title', '')}"

        # Кнопка переключения категории
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"toggle_category_{cat_id}")])

        # Если категория открыта, добавляем её содержимое в сообщение
        if is_open:
            message += f"\n**{category.get('title', '')}**\n"
            message += f"_{category.get('description', '')}_\n\n"

            for item in category.get('items', []):
                message += f"• {item}\n"

            message += "\n"

    # Кнопка "Продолжить практику"
    keyboard.append([InlineKeyboardButton("✅ Продолжить практику", callback_data="continue_from_examples")])

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def handle_category_toggle(query, user, db, category_id, opened_categories):
    """Переключить состояние категории (открыть/закрыть)"""
    if category_id in opened_categories:
        opened_categories.remove(category_id)
    else:
        opened_categories.add(category_id)

    # Перерисовать меню с обновлённым состоянием
    await handle_show_examples(query, user, db, opened_categories)


async def handle_show_recipes(query, user, db, context=None, opened_recipes=None):
    """
    Показать рецепты с микрозеленью в виде разворачивающихся кнопок

    Args:
        query: CallbackQuery объект
        user: User объект из БД
        db: Database session
        context: CallbackContext для хранения состояния
        opened_recipes: Set[str] - множество ID развернутых рецептов (опционально)
    """
    recipes = practices_manager.get_recipes()

    # Получить состояние развернутых рецептов
    if opened_recipes is None:
        if context and hasattr(context, 'user_data'):
            opened_recipes = context.user_data.get('opened_recipes', set())
        else:
            opened_recipes = set()

    # Формируем сообщение
    message = f"**{recipes.get('title', 'Рецепты')}** 🍽\n\n"
    message += recipes.get('message', '')

    items = recipes.get('items', [])

    # Добавляем развернутые рецепты в текст сообщения
    for recipe in items:
        recipe_id = recipe.get('id', '')
        if recipe_id in opened_recipes:
            message += f"\n\n**{recipe.get('title', '')}**\n"
            message += f"_{recipe.get('subtitle', '')}_\n\n"
            message += f"**Ингредиенты:** {recipe.get('ingredients', '')}\n"
            message += f"**Как делать:** {recipe.get('instructions', '')}\n"

            if recipe.get('secret'):
                message += f"**В чём секрет:** {recipe.get('secret')}\n"

            if recipe.get('meaning'):
                message += f"**Смысл:** {recipe.get('meaning')}\n"

    # Создаем кнопки для всех рецептов
    keyboard = []
    for recipe in items:
        recipe_id = recipe.get('id', '')
        title = recipe.get('title', '')

        # Кнопка для сворачивания или разворачивания
        if recipe_id in opened_recipes:
            # Рецепт развернут - кнопка для сворачивания
            button_text = f"▼ {title}"
            callback_data = f"collapse_recipe_{recipe_id}"
        else:
            # Рецепт свернут - кнопка для разворачивания
            button_text = title
            callback_data = f"expand_recipe_{recipe_id}"

        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    # Добавляем кнопку для продолжения
    # Для Stage 4 - переход к следующему шагу (Step 16)
    # Для Stage 5 (daily practices) - использовать next_daily_substep
    if user.current_stage == 4:
        keyboard.append([InlineKeyboardButton("✅ Продолжить", callback_data="next_step")])
    else:
        keyboard.append([InlineKeyboardButton("✅ Завершить практику", callback_data="next_daily_substep")])

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

    logger.info(f"Пользователь {user.telegram_id} просматривает меню рецептов (развернуто: {opened_recipes})")


async def handle_recipe_toggle(query, user, db, recipe_id, opened_recipes, context):
    """
    Переключить состояние рецепта (развернуть/свернуть)

    Args:
        query: CallbackQuery объект
        user: User объект из БД
        db: Database session
        recipe_id: str - ID рецепта для переключения
        opened_recipes: Set[str] - множество ID развернутых рецептов
        context: CallbackContext для хранения состояния
    """
    # Переключить состояние рецепта
    if recipe_id in opened_recipes:
        opened_recipes.remove(recipe_id)
        logger.info(f"Пользователь {user.telegram_id} свернул рецепт {recipe_id}")
    else:
        opened_recipes.add(recipe_id)
        logger.info(f"Пользователь {user.telegram_id} развернул рецепт {recipe_id}")

    # Сохранить состояние в context
    if context and hasattr(context, 'user_data'):
        context.user_data['opened_recipes'] = opened_recipes

    # Перерисовать меню с обновлённым состоянием
    await handle_show_recipes(query, user, db, context, opened_recipes)


async def handle_show_manifesto(query, user, db):
    """Показать Манифест Предвкушения"""
    manifesto = practices_manager.get_manifesto()

    message = f"**{manifesto.get('title', 'Манифест')}**\n\n"
    message += manifesto.get('message', '') + "\n\n"

    principles = manifesto.get('principles', [])
    for principle in principles:
        message += f"\n**{principle.get('number')}.**\n{principle.get('text', '')}\n"

    message += f"\n\n{manifesto.get('closing', '')}"

    await query.edit_message_text(message, parse_mode='Markdown')
    logger.info(f"Пользователь {user.telegram_id} получил Манифест Предвкушения")


async def handle_start_daily_practices(query, user, db):
    """
    Начать ежедневные практики Stage 5 (До беби-лифа)
    Переводит пользователя на Stage 5 и устанавливает режим ожидания первого напоминания
    """
    from datetime import date

    # Перевести пользователя на Stage 5, первый день
    update_user_progress(db, user.telegram_id, stage_id=5, step_id=17, day=user.current_day)

    # Установить режим ожидания первого напоминания (day=0)
    user.daily_practice_day = 0  # 0 = ожидание первого напоминания
    user.daily_practice_substep = ""
    user.last_practice_date = None
    user.reminder_postponed = False
    user.postponed_until = None
    db.commit()

    logger.info(f"Пользователь {user.telegram_id} начал Stage 5 (ежедневные практики до беби-лифа)")

    # Показать подтверждающее сообщение
    await query.edit_message_text(
        "✅ **Отлично! Начинаем новый цикл.**\n\n"
        "Следующие 7 дней ты будешь получать ежедневные практики в установленное время.\n\n"
        "Каждый день — новая тема для работы с долгосрочными целями.\n\n"
        "🌱 Первое напоминание придет завтра в твоё предпочтительное время!",
        parse_mode='Markdown'
    )


async def handle_sprouts_appeared(query, user, db):
    """Обработать нажатие кнопки 'У меня появились первые всходы!'"""
    # Проверить, что пользователь на Этапе 1
    if user.current_stage != 1:
        await query.edit_message_text(
            "Эта функция доступна только на Этапе 1 (после посадки).\n\n"
            "Используйте /status для проверки вашего прогресса."
        )
        return

    # Перевести пользователя на Этап 2, Шаг 7 (первый шаг этапа, день 2)
    update_user_progress(db, user.telegram_id, stage_id=2, step_id=7, day=2)

    # Получить первый шаг Этапа 2
    stage2 = practices_manager.get_stage(2)
    if not stage2:
        await query.edit_message_text("Ошибка: не найден Этап 2")
        return

    first_step = stage2['steps'][0]

    # Сформировать сообщение
    message = "🎉 **Отлично! Ваши всходы появились!**\n\n"
    message += f"**{first_step.get('title', '')}**\n\n"
    message += first_step.get('message', '')

    # Создать клавиатуру с кнопками
    buttons = first_step.get('buttons', [])
    keyboard = create_practice_keyboard(buttons)

    # Отправить новый этап
    await query.edit_message_text(
        message,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    logger.info(f"Пользователь {user.telegram_id} подтвердил всходы, переведён на Этап 2")


async def handle_continue_practice(query, user, db):
    """Обработать нажатие кнопки 'Продолжить практику' из /status"""
    logger.info(f"Пользователь {user.telegram_id} нажал 'Продолжить практику'")

    # Получить текущий шаг пользователя
    current_stage = user.current_stage
    current_step_id = user.current_step

    # Получить данные этапа
    stage = practices_manager.get_stage(current_stage)
    if not stage:
        await query.edit_message_text(
            f"❌ Не удалось найти Этап {current_stage}\n\n"
            "Пожалуйста, свяжитесь с поддержкой: /contact"
        )
        logger.error(f"Не найден этап: stage_id={current_stage}")
        return

    # Получить данные шага из practices.json
    step = practices_manager.get_step(stage_id=current_stage, step_id=current_step_id)

    # Если шаг не найден по step_id, попробуем найти первый шаг этапа
    if not step:
        logger.warning(f"Не найден шаг по step_id={current_step_id}, берем первый шаг этапа {current_stage}")
        steps = stage.get('steps', [])
        if steps:
            step = steps[0]
            # Обновить current_step в базе на правильный step_id
            correct_step_id = step.get('step_id')
            user.current_step = correct_step_id
            db.commit()
            logger.info(f"Исправлен current_step для пользователя {user.telegram_id}: {current_step_id} -> {correct_step_id}")
        else:
            await query.edit_message_text(
                f"❌ Этап {current_stage} не содержит практик\n\n"
                "Пожалуйста, свяжитесь с поддержкой: /contact"
            )
            logger.error(f"Этап {current_stage} пуст")
            return

    # Сформировать сообщение с практикой
    message = f"**{step.get('title', 'Практика')}**\n\n"
    message += step.get('message', '')

    # Создать клавиатуру с кнопками
    buttons = step.get('buttons', [])
    keyboard = create_practice_keyboard(buttons)

    # Отправить практику
    await query.edit_message_text(
        message,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    logger.info(f"Пользователь {user.telegram_id} продолжил практику: stage={current_stage}, step={step.get('step_id')}")


async def handle_confirm_reset(query, user, db):
    """Подтвердить сброс прогресса и начать заново"""
    from utils.db import reset_user_progress, update_user_progress
    from datetime import datetime

    # Сбросить прогресс пользователя
    reset_user_progress(db, user.telegram_id)

    # Получить первый шаг первого этапа
    first_step = practices_manager.get_step(stage_id=1, step_id=1)

    if not first_step:
        await query.edit_message_text(
            "😞 Извините, произошла ошибка при загрузке практик.\n"
            "Пожалуйста, попробуйте позже."
        )
        logger.error(f"Не удалось загрузить первый шаг практики для пользователя {user.telegram_id}")
        return

    # Обновить прогресс пользователя
    update_user_progress(db, user.telegram_id, stage_id=1, step_id=1, day=1)

    # Установить started_at
    user.started_at = datetime.utcnow()
    db.commit()

    # Сформировать сообщение первого шага
    message = f"�� **Прогресс сброшен!**\n\n"
    message += f"Начнём сначала! 🌱\n\n"
    message += f"**{first_step.get('title', 'Практика')}**\n\n"
    message += first_step.get('message', '')

    # Создать клавиатуру с кнопками первого шага
    buttons = first_step.get('buttons', [])
    keyboard = create_practice_keyboard(buttons)

    # Отправить первый шаг
    await query.edit_message_text(
        message,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    logger.info(f"Пользователь {user.telegram_id} подтвердил сброс прогресса и начал практику")


async def handle_start_practice_after_reset(query, user, db):
    """Начать практику после сброса прогресса"""
    from utils.db import update_user_progress
    from datetime import datetime

    logger.info(f"[DEBUG] handle_start_practice_after_reset вызван для пользователя {user.telegram_id}")

    # Получить первый шаг первого этапа (stage_id=1, step_id=1)
    first_step = practices_manager.get_step(stage_id=1, step_id=1)
    logger.info(f"[DEBUG] first_step получен: {first_step is not None}")

    if not first_step:
        await query.edit_message_text(
            "😞 Извините, произошла ошибка при загрузке практик.\n"
            "Пожалуйста, попробуйте позже или свяжитесь с поддержкой: /contact"
        )
        logger.error(f"Не удалось загрузить первый шаг практики для пользователя {user.telegram_id}")
        return

    # Обновить прогресс пользователя
    update_user_progress(db, user.telegram_id, stage_id=1, step_id=1, day=1)
    logger.info(f"[DEBUG] Прогресс обновлен")

    # Установить started_at
    user.started_at = datetime.utcnow()
    db.commit()
    logger.info(f"[DEBUG] started_at установлен")

    # Сформировать сообщение
    message = f"**{first_step.get('title', 'Начало практики')}**\n\n"
    message += first_step.get('message', '')
    logger.info(f"[DEBUG] Сообщение сформировано, длина: {len(message)}")

    # Создать клавиатуру с кнопками
    buttons = first_step.get('buttons', [])
    keyboard = create_practice_keyboard(buttons)
    logger.info(f"[DEBUG] Клавиатура создана, кнопок: {len(buttons)}")

    # Отправить первый шаг
    try:
        await query.edit_message_text(
            message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
        logger.info(f"[DEBUG] Сообщение отправлено успешно")
    except Exception as e:
        logger.error(f"[DEBUG] Ошибка при отправке сообщения: {e}")
        raise

    logger.info(f"Пользователь {user.telegram_id} начал практику после сброса")


async def handle_cancel_reset(query, user, db):
    """Отменить сброс и вернуться к текущей практике"""
    # Получить текущий шаг пользователя
    current_stage = user.current_stage
    current_step_id = user.current_step

    # Получить данные этапа
    stage = practices_manager.get_stage(current_stage)
    if not stage:
        await query.edit_message_text(
            "❌ Сброс отменён.\n\n"
            f"Не удалось загрузить вашу текущую практику.\n"
            "Используйте /status для проверки прогресса."
        )
        logger.error(f"Не найден этап: stage_id={current_stage}")
        return

    # Получить данные шага
    step = practices_manager.get_step(stage_id=current_stage, step_id=current_step_id)

    # Если шаг не найден, взять первый шаг этапа
    if not step:
        logger.warning(f"Не найден шаг по step_id={current_step_id}, берем первый шаг этапа {current_stage}")
        steps = stage.get('steps', [])
        if steps:
            step = steps[0]
            correct_step_id = step.get('step_id')
            user.current_step = correct_step_id
            db.commit()
        else:
            await query.edit_message_text(
                "❌ Сброс отменён.\n\n"
                "Используйте /status для проверки прогресса."
            )
            return

    # Сформировать сообщение с текущей практикой
    message = "✅ **Сброс отменён!**\n\n"
    message += f"Возвращаемся к вашей практике:\n\n"
    message += f"**{step.get('title', 'Практика')}**\n\n"
    message += step.get('message', '')

    # Создать клавиатуру с кнопками
    buttons = step.get('buttons', [])
    keyboard = create_practice_keyboard(buttons)

    # Отправить текущую практику
    await query.edit_message_text(
        message,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    logger.info(f"Пользователь {user.telegram_id} отменил сброс, возврат к практике: stage={current_stage}, step={step.get('step_id')}")


async def handle_start_waiting_for_daily(query, user, db):
    """Начать ожидание ежедневных практик"""
    # Установить режим ожидания ежедневных практик
    user.daily_practice_day = 0  # 0 = ожидание первой практики
    db.commit()

    await query.edit_message_text(
        "✅ Отлично! Я буду присылать напоминания о практиках.\n\n"
        "Первое напоминание придёт в твоё предпочтительное время.\n\n"
        "🌱 До встречи на практике!",
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user.telegram_id} начал ожидание ежедневных практик")


async def handle_complete_daily_practice(query, user, db):
    """Завершить ежедневную практику"""
    from datetime import date

    current_day = user.daily_practice_day

    # Если это была последняя ежедневная практика (день 4)
    if current_day >= 4:
        # Переходим к этапу 4 (день 7 - первый урожай), шаг 12
        update_user_progress(db, user.telegram_id, stage_id=4, step_id=12, day=user.current_day)
        user.daily_practice_day = 0
        user.last_practice_date = None
        user.reminder_postponed = False
        user.postponed_until = None
        db.commit()

        await query.edit_message_text(
            "🎉 **Все 4 дня практик «Свидетель» завершены!**\n\n"
            "Отличная работа! Ты освоил(а) навык не-вмешательства.\n\n"
            "Скоро мы перейдём к практике первого урожая!\n\n"
            "Используйте /continue_practice для продолжения.",
            parse_mode='Markdown'
        )
        logger.info(f"Пользователь {user.telegram_id} завершил все ежедневные практики, переход к этапу 4")
    else:
        # Увеличить счётчик дня и сохранить дату
        user.daily_practice_day = current_day + 1
        user.last_practice_date = date.today().strftime('%Y-%m-%d')
        user.reminder_postponed = False
        user.postponed_until = None
        db.commit()

        await query.edit_message_text(
            f"✅ **Практика дня {current_day} завершена!**\n\n"
            f"Молодец! Ты сделал(а) ещё один шаг в развитии навыка наблюдения.\n\n"
            f"До встречи завтра! 🌱",
            parse_mode='Markdown'
        )
        logger.info(f"Пользователь {user.telegram_id} завершил практику дня {current_day}, переход к дню {current_day + 1}")


async def handle_postpone_reminder(query, user, db):
    """Отложить напоминание на 2 часа"""
    from datetime import datetime, timedelta

    postponed_time = datetime.now() + timedelta(hours=2)
    user.reminder_postponed = True
    user.postponed_until = postponed_time
    db.commit()

    await query.edit_message_text(
        f"⏰ **Напоминание отложено**\n\n"
        f"Я напомню тебе о практике через 2 часа.\n\n"
        f"Время напоминания: {postponed_time.strftime('%H:%M')}\n\n"
        f"До встречи! 🌱",
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user.telegram_id} отложил напоминание до {postponed_time}")


async def handle_view_daily_practice(query, user, db):
    """Показать текущую ежедневную практику (для кнопки 'Назад')"""
    current_day = user.daily_practice_day

    # Получить практику текущего дня
    stage = practices_manager.get_stage(3)
    if not stage:
        await query.edit_message_text("Ошибка: этап 3 не найден")
        return

    daily_practices = stage.get('daily_practices', [])
    practice = None
    for p in daily_practices:
        if p.get('day') == current_day:
            practice = p
            break

    if not practice:
        await query.edit_message_text(f"Ошибка: практика дня {current_day} не найдена")
        return

    # Показать практику
    message = f"**{practice.get('title', 'Практика')}**\n\n"
    message += practice.get('message', '')

    buttons = practice.get('buttons', [])
    keyboard = create_practice_keyboard(buttons)

    await query.edit_message_text(
        message,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user.telegram_id} вернулся к практике дня {current_day}")


async def handle_test_daily_reminder(query, user, db, context):
    """
    Админская функция: отправить тестовое напоминание о ежедневной практике
    """
    # Проверка прав администратора
    if not is_admin(user.telegram_id):
        await query.answer("⛔ Эта функция доступна только администраторам", show_alert=True)
        logger.warning(f"Пользователь {user.telegram_id} попытался использовать test_daily_reminder без прав")
        return

    try:
        # Получить данные пользователя из БД
        db_user = db.query(User).filter(User.telegram_id == user.telegram_id).first()

        if not db_user:
            await query.answer("❌ Ошибка: пользователь не найден в БД", show_alert=True)
            return

        # Установить daily_practice_day если он 0 (начать первый день)
        if db_user.daily_practice_day == 0:
            db_user.daily_practice_day = 1
            db.commit()
            logger.info(f"Установлен daily_practice_day=1 для пользователя {user.telegram_id} (тест-напоминание)")

        # Отправить тестовое напоминание
        await send_daily_practice_reminder(context.bot, db_user, db)

        await query.answer("✅ Тестовое напоминание отправлено!", show_alert=True)
        logger.info(f"Администратор {user.telegram_id} отправил себе тестовое напоминание о ежедневной практике")

    except Exception as e:
        await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
        logger.error(f"Ошибка при отправке тестового напоминания для админа {user.telegram_id}: {e}")


async def handle_complete_day4_practice(query, user, db, context):
    """
    Завершить практику дня 4 (переход к Stage 4)
    """
    await _complete_daily_practice_flow(query, user, db, {
        "message": "Переход к этапу 4..."
    }, context)
    logger.info(f"Пользователь {user.telegram_id} завершил день 4, переход к Stage 4")


async def handle_test_stage4_reminder(query, user, db, context):
    """
    Тестовая кнопка для администратора: отправить тестовое напоминание о Stage 4
    """
    from utils.scheduler import send_stage4_reminder

    try:
        # Проверить права администратора
        if user.telegram_id not in ADMIN_IDS:
            await query.answer("⛔ Эта функция доступна только администраторам", show_alert=True)
            return

        # Получить данные пользователя из БД
        db_user = db.query(User).filter(User.telegram_id == user.telegram_id).first()

        if not db_user:
            await query.answer("❌ Ошибка: пользователь не найден в БД", show_alert=True)
            return

        # Отправить тестовое напоминание о Stage 4
        await send_stage4_reminder(context.bot, db_user, db)

        await query.answer("✅ Тестовое напоминание о Stage 4 отправлено!", show_alert=True)
        logger.info(f"Администратор {user.telegram_id} отправил себе тестовое напоминание о Stage 4")

    except Exception as e:
        await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
        logger.error(f"Ошибка при отправке тестового напоминания Stage 4 для админа {user.telegram_id}: {e}")


async def handle_start_stage6_finale(query, user, db):
    """
    Начать финальные практики Stage 6 с первого шага (Step 24)

    Показывает Step 24 с его контентом из practices.json
    """
    logger.info(f"Пользователь {user.telegram_id} начинает финальные практики Stage 6")

    # Убедиться что пользователь на Stage 6
    if user.current_stage != 6:
        from utils.db import update_user_progress
        update_user_progress(db, user.telegram_id, stage_id=6, step_id=24, day=user.current_day)

    # Получить Step 24
    stage = practices_manager.get_stage(6)
    if not stage:
        await query.edit_message_text("Ошибка: Stage 6 не найден")
        return

    steps = stage.get('steps', [])
    step = None
    for s in steps:
        if s.get('step_id') == 24:
            step = s
            break

    if not step:
        await query.edit_message_text("Ошибка: Step 24 не найден")
        return

    # Показать Step 24
    message = f"**{step.get('title', '')}**\n\n{step.get('message', '')}"

    # Создать кнопки из practices.json
    buttons_data = step.get('buttons', [])
    keyboard = create_practice_keyboard(buttons_data)

    await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')

    logger.info(f"Пользователь {user.telegram_id} начал Step 24 (Stage 6)")


# ==================== СЦЕНАРИЙ "САЛАТ НЕ ВЗОШЁЛ" ====================

async def handle_replant_start(query, user, db):
    """Начать сценарий 'Салат не взошёл' - показать шаг 1"""
    logger.info(f"Пользователь {user.telegram_id} начал сценарий 'Салат не взошёл'")
    await handle_replant_step(query, user, db, 1)


async def handle_replant_step(query, user, db, step_id: int):
    """Показать указанный шаг сценария 'Салат не взошёл'"""
    replant = practices_manager.get_replant_scenario()
    if not replant:
        await query.edit_message_text("Ошибка: сценарий не найден")
        return

    step = None
    for s in replant.get('steps', []):
        if s.get('step_id') == step_id:
            step = s
            break

    if not step:
        await query.edit_message_text(f"Ошибка: шаг {step_id} не найден")
        return

    message = f"**{step.get('title', '')}**\n\n{step.get('message', '')}"
    keyboard = create_practice_keyboard(step.get('buttons', []))

    await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
    logger.info(f"Пользователь {user.telegram_id} на шаге {step_id} сценария 'Салат не взошёл'")


async def handle_replant_complete(query, user, db):
    """Завершить сценарий и вернуть в режим ожидания всходов"""
    from datetime import datetime

    logger.info(f"Пользователь {user.telegram_id} завершает сценарий 'Салат не взошёл'")

    # Сбросить состояние на ожидание всходов
    user.awaiting_sprouts = True
    user.started_at = datetime.utcnow()  # Сбросить таймер
    db.commit()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Всходы появились!", callback_data="sprouts_appeared")]
    ])

    await query.edit_message_text(
        "🌱 **Семена посажены заново!**\n\n"
        "Таймер сброшен. Жди новых всходов — обычно они появляются через 2-4 дня.\n\n"
        "Я буду присылать напоминания проверить горшок.\n\n"
        "Как только увидишь первые зелёные петельки — нажми кнопку! 🌱",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

    logger.info(f"Пользователь {user.telegram_id} завершил сценарий 'Салат не взошёл', started_at сброшен")


# ==================== СЦЕНАРИЙ "ПЛЕСЕНЬ" ====================

async def handle_mold_start(query, user, db):
    """Показать инструкцию по борьбе с плесенью"""
    logger.info(f"Пользователь {user.telegram_id} начал сценарий 'Плесень'")

    mold = practices_manager.get_mold_scenario()
    if not mold:
        await query.edit_message_text("Ошибка: сценарий не найден")
        return

    message = f"**{mold.get('title', '')}**\n\n{mold.get('message', '')}"
    keyboard = create_practice_keyboard(mold.get('buttons', []))

    await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')


async def handle_mold_complete(query, user, db):
    """Завершить сценарий плесени и вернуть в режим ожидания (БЕЗ сброса таймера)"""
    logger.info(f"Пользователь {user.telegram_id} завершает сценарий 'Плесень'")

    # НЕ сбрасываем таймер - просто возвращаем в ожидание
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Всходы появились!", callback_data="sprouts_appeared")],
        [InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_start")]
    ])

    await query.edit_message_text(
        "🌱 **Отлично!**\n\n"
        "Ты справился(ась) с плесенью. Продолжай наблюдать за своим горшком.\n\n"
        "Как только увидишь первые зелёные петельки — нажми кнопку! 🌱",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user.telegram_id} завершил сценарий 'Плесень'")


async def handle_mold_sprouts_start(query, user, db):
    """Показать инструкцию по борьбе с плесенью (для ростков на воздухе - Stage 3-5)"""
    logger.info(f"Пользователь {user.telegram_id} начал сценарий 'Плесень на ростках'")

    mold = practices_manager.get_mold_sprouts_scenario()
    if not mold:
        await query.edit_message_text("Ошибка: сценарий не найден")
        return

    message = f"**{mold.get('title', '')}**\n\n{mold.get('message', '')}"
    keyboard = create_practice_keyboard(mold.get('buttons', []))

    await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')


async def handle_mold_sprouts_complete(query, user, db):
    """Завершить сценарий плесени и вернуть к напоминанию текущего этапа (БЕЗ сброса таймера)"""
    logger.info(f"Пользователь {user.telegram_id} завершает сценарий 'Плесень на ростках'")

    current_stage = user.current_stage
    current_day = user.daily_practice_day or 1

    # Возвращаем к напоминанию в зависимости от этапа
    if current_stage == 3:
        # Stage 3: ежедневные практики
        stage = practices_manager.get_stage(3)
        if stage:
            daily_practices = stage.get('daily_practices', [])
            practice = None
            for p in daily_practices:
                if p.get('day') == current_day:
                    practice = p
                    break

            if practice:
                reminder = practice.get('reminder', {})
                message = reminder.get('message', '')
                buttons = reminder.get('buttons', [])
                keyboard_buttons = []
                for button in buttons:
                    text = button.get('text', '')
                    action = button.get('action', '')
                    if text and action:
                        keyboard_buttons.append([InlineKeyboardButton(text, callback_data=action)])
                keyboard_buttons.append([InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_sprouts_start")])
                keyboard = InlineKeyboardMarkup(keyboard_buttons)

                await query.edit_message_text(
                    f"🌱 **Отлично!** Ты справился(ась) с плесенью.\n\n{message}",
                    reply_markup=keyboard,
                    parse_mode='Markdown'
                )
                logger.info(f"Пользователь {user.telegram_id} вернулся к напоминанию Stage 3 день {current_day}")
                return

    elif current_stage == 4:
        # Stage 4: якорь
        stage = practices_manager.get_stage(4)
        if stage:
            steps = stage.get('steps', [])
            if steps:
                first_step = steps[0]
                message = f"🌱 **Отлично!** Ты справился(ась) с плесенью.\n\n"
                message += f"**{first_step.get('title', '')}**\n\n"
                message += first_step.get('message', '')

                buttons_data = first_step.get('buttons', [])
                keyboard_buttons = []
                if buttons_data:
                    for btn in buttons_data:
                        keyboard_buttons.append([InlineKeyboardButton(btn['text'], callback_data=btn['action'])])
                else:
                    keyboard_buttons.append([InlineKeyboardButton("Начать практику", callback_data="next_step")])
                keyboard_buttons.append([InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_sprouts_start")])
                keyboard = InlineKeyboardMarkup(keyboard_buttons)

                await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
                logger.info(f"Пользователь {user.telegram_id} вернулся к напоминанию Stage 4")
                return

    elif current_stage == 5:
        # Stage 5: ежедневные практики до беби-лифа
        stage = practices_manager.get_stage(5)
        if stage:
            daily_practices = stage.get('daily_practices', [])
            practice = None
            for p in daily_practices:
                if p.get('day') == current_day:
                    practice = p
                    break

            if practice:
                theme = practice.get('theme', '')
                message = f"🌱 **Отлично!** Ты справился(ась) с плесенью.\n\n"
                message += f"**День {current_day} из 7: {theme}**\n\n"
                message += f"Пришло время ежедневной практики с долгосрочными целями.\n\n"
                message += f"Сегодня мы поработаем с темой «{theme}»."

                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("Начать практику", callback_data="stage5_start_substep")],
                    [InlineKeyboardButton("Напомнить позже", callback_data="postpone_reminder")],
                    [InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_sprouts_start")]
                ])

                await query.edit_message_text(message, reply_markup=keyboard, parse_mode='Markdown')
                logger.info(f"Пользователь {user.telegram_id} вернулся к напоминанию Stage 5 день {current_day}")
                return

    # Fallback - если не удалось определить этап
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Продолжить практику", callback_data="continue_practice")]
    ])

    await query.edit_message_text(
        "🌱 **Отлично!**\n\n"
        "Ты справился(ась) с плесенью. Возвращайся к практике!",
        reply_markup=keyboard,
        parse_mode='Markdown'
    )
    logger.info(f"Пользователь {user.telegram_id} завершил сценарий 'Плесень на ростках'")
