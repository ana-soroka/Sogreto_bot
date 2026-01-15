"""
Обработчики команд практик:
/start_practice и работа с практиками
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import error_handler, practices_manager
from utils.db import get_or_create_user, update_user_progress
from models import SessionLocal

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
            await handle_show_recipes(query, user, db)
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

    # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ЭТАПА 1: не переходим сразу на этап 2
    if current_stage == 1:
        # Установить флаг ожидания всходов
        user.awaiting_sprouts = True
        db.commit()

        # Показать сообщение с кнопкой
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🌱 Появились первые всходы!", callback_data="sprouts_appeared")]
        ])

        await query.edit_message_text(
            f"🎉 **Этап 1 завершён!**\n\n"
            f"Отличная работа! Семена посажены, и теперь начинается самое волнующее — ожидание.\n\n"
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
        logger.info(f"Пользователь {user.telegram_id} завершил этап 1, ожидает всходы")
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


async def handle_show_recipes(query, user, db):
    """Показать рецепты с микрозеленью"""
    recipes = practices_manager.get_recipes()

    message = f"**{recipes.get('title', 'Рецепты')}** 🍽\n\n"
    message += recipes.get('message', '') + "\n\n"

    items = recipes.get('items', [])
    for recipe in items[:3]:  # Показать первые 3 рецепта
        message += f"\n{recipe.get('title', '')}\n"
        message += f"_{recipe.get('subtitle', '')}_\n\n"
        message += f"**Ингредиенты:** {recipe.get('ingredients', '')}\n"
        message += f"**Приготовление:** {recipe.get('instructions', '')}\n"

        if recipe.get('secret'):
            message += f"💡 {recipe.get('secret')}\n"

        message += "\n"

    # Кнопка завершения этапа
    keyboard = [[InlineKeyboardButton("Завершить этап", callback_data="complete_stage")]]

    await query.edit_message_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


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
    """Начать ежедневные практики (этап 5)"""
    # TODO: Реализовать ежедневные практики на следующем этапе
    await query.edit_message_text(
        "📅 **Ежедневные практики**\n\n"
        "Функция ежедневных практик будет реализована на следующем этапе разработки.\n\n"
        "Пока используйте /status для отслеживания прогресса."
    )
    logger.info(f"Пользователь {user.telegram_id} попытался начать ежедневные практики")


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
    message += f"Переходим к **{stage2['stage_name']}**\n\n"
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
    from utils.db import reset_user_progress

    # Сбросить прогресс пользователя
    reset_user_progress(db, user.telegram_id)

    await query.edit_message_text(
        "🔄 **Прогресс сброшен!**\n\n"
        "Вы можете начать практики заново командой /start_practice\n\n"
        "Начнём сначала! 🌱"
    )

    logger.info(f"Пользователь {user.telegram_id} подтвердил сброс прогресса")


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
