"""
VK обработчики практик — порт handlers/practices.py для ВКонтакте
Полный роутинг всех callback-действий практик.
"""
import json
import logging
import asyncio
from datetime import datetime, date, timedelta

from models import SessionLocal, User
from utils import practices_manager
from utils.db import get_or_create_vk_user, update_user_progress_obj, reset_user_progress_obj
from utils.formatting import markdown_to_plain
from utils.vk_keyboards import create_vk_inline_keyboard, create_vk_callback_keyboard

logger = logging.getLogger(__name__)

# In-memory state для VK (аккордеоны примеров/рецептов)
_user_state = {}


# ==================== ХЕЛПЕРЫ ====================

async def _edit(api, peer_id, cmid, message, keyboard=None):
    """Редактировать сообщение VK"""
    kwargs = {"peer_id": peer_id, "conversation_message_id": cmid, "message": message}
    if keyboard:
        kwargs["keyboard"] = keyboard
    await api.messages.edit(**kwargs)


async def _send(api, peer_id, message, keyboard=None):
    """Отправить новое сообщение VK"""
    kwargs = {"peer_id": peer_id, "message": message, "random_id": 0}
    if keyboard:
        kwargs["keyboard"] = keyboard
    await api.messages.send(**kwargs)


def _get_user(db, vk_id):
    """Получить VK-пользователя из БД"""
    return db.query(User).filter_by(vk_id=vk_id).first()


def _practice_kb(buttons_data):
    """Создать VK-клавиатуру из кнопок practices.json"""
    return create_vk_inline_keyboard(buttons_data)


def _step_message(step):
    """Сформировать текст шага (без Markdown)"""
    title = step.get('title', 'Практика')
    msg = step.get('message', '')
    return markdown_to_plain(f"{title}\n\n{msg}")


# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ DAILY PRACTICES ====================

def _get_daily_practice_by_day(stage, day):
    """Получить практику по номеру дня"""
    for practice in stage.get('daily_practices', []):
        if practice.get('day') == day:
            return practice
    return None


def _get_substep_by_id(daily_practice, substep_id):
    """Получить подшаг по substep_id"""
    for substep in daily_practice.get('substeps', []):
        if substep.get('substep_id') == substep_id:
            return substep
    return None


def _get_next_substep_id(current_substep_id):
    """Определить следующий подшаг"""
    flow = {
        "intro": "practice",
        "practice": "checkin",
        "practice2": "checkin",
        "response_A": "completion",
        "response_B": "completion"
    }
    return flow.get(current_substep_id, "completion")


async def _send_substep_message_vk(api, peer_id, cmid, substep):
    """Отправить сообщение подшага с VK-кнопками"""
    title = substep.get('title', '')
    message = substep.get('message', '')
    full_message = f"{title}\n\n{message}" if title else message
    full_message = markdown_to_plain(full_message)

    substep_id = substep.get('substep_id', '')

    if substep_id in ["practice", "practice2"]:
        # VK: нет WebApp таймера, заменяем кнопками
        keyboard = create_vk_callback_keyboard([
            ("← Назад", "prev_daily_substep"),
            ("Минута прошла", "next_daily_substep"),
        ])
    else:
        buttons = substep.get('buttons', [])
        keyboard = create_vk_inline_keyboard(buttons) if buttons else None

    await _edit(api, peer_id, cmid, full_message, keyboard)


# ==================== ГЛАВНЫЙ РОУТЕР ====================

async def vk_handle_practice_callback(api, peer_id, user_id, cmid, action):
    """Главный роутер callback-кнопок практик"""
    logger.info(f"[VK] Пользователь {user_id} нажал: {action}")

    db = SessionLocal()
    try:
        user = _get_user(db, user_id)
        if not user:
            try:
                users = await api.users.get(user_ids=[user_id])
                first_name = users[0].first_name if users else None
                last_name = users[0].last_name if users else None
            except:
                first_name, last_name = None, None
            user = get_or_create_vk_user(db, vk_id=user_id, first_name=first_name, last_name=last_name)

        # --- Навигация по шагам ---
        if action == "next_step":
            await _handle_next_step(api, peer_id, cmid, user, db)
        elif action == "prev_step":
            await _handle_prev_step(api, peer_id, cmid, user, db)
        elif action == "complete_stage":
            await _handle_complete_stage(api, peer_id, cmid, user, db)

        # --- Примеры ---
        elif action == "show_examples_menu":
            _user_state.setdefault(user_id, {})['opened_categories'] = set()
            await _handle_show_examples(api, peer_id, cmid, user, db, user_id)
        elif action.startswith("toggle_category_"):
            cat_id = action.replace("toggle_category_", "")
            state = _user_state.setdefault(user_id, {})
            opened = state.setdefault('opened_categories', set())
            if cat_id in opened:
                opened.remove(cat_id)
            else:
                opened.add(cat_id)
            await _handle_show_examples(api, peer_id, cmid, user, db, user_id)
        elif action == "continue_from_examples":
            _user_state.pop(user_id, None)
            await _handle_next_step(api, peer_id, cmid, user, db)

        # --- Рецепты ---
        elif action == "show_recipes":
            _user_state.setdefault(user_id, {})['opened_recipes'] = set()
            await _handle_show_recipes(api, peer_id, cmid, user, db, user_id)
        elif action.startswith("expand_recipe_") or action.startswith("collapse_recipe_"):
            recipe_id = action.replace("expand_recipe_", "").replace("collapse_recipe_", "")
            state = _user_state.setdefault(user_id, {})
            opened = state.setdefault('opened_recipes', set())
            if recipe_id in opened:
                opened.remove(recipe_id)
            else:
                opened.add(recipe_id)
            await _handle_show_recipes(api, peer_id, cmid, user, db, user_id)

        # --- Манифест ---
        elif action == "show_manifesto":
            await _handle_show_manifesto(api, peer_id, cmid, user, db)

        # --- Ежедневные практики Stage 3 ---
        elif action == "start_waiting_for_daily":
            await _handle_start_waiting_for_daily(api, peer_id, cmid, user, db)
        elif action == "start_daily_substep":
            await _handle_start_daily_substep(api, peer_id, cmid, user, db)
        elif action == "next_daily_substep":
            await _handle_next_daily_substep(api, peer_id, cmid, user, db)
        elif action == "prev_daily_substep":
            await _handle_prev_daily_substep(api, peer_id, cmid, user, db)
        elif action == "daily_choice_A":
            await _handle_daily_choice(api, peer_id, cmid, user, db, "response_A")
        elif action == "daily_choice_B":
            await _handle_daily_choice(api, peer_id, cmid, user, db, "response_B")
        elif action == "complete_daily_practice":
            await _handle_complete_daily_practice(api, peer_id, cmid, user, db)
        elif action == "complete_day4_practice":
            await _handle_complete_day4_practice(api, peer_id, cmid, user, db)
        elif action == "postpone_reminder":
            await _handle_postpone_reminder(api, peer_id, cmid, user, db)
        elif action == "view_daily_practice":
            await _handle_view_daily_practice(api, peer_id, cmid, user, db)

        # --- Stage 5 ---
        elif action == "start_daily_practices":
            await _handle_start_daily_practices(api, peer_id, cmid, user, db)
        elif action == "stage5_start_substep":
            from vk_handlers.practices_stage5 import vk_handle_stage5_start
            await vk_handle_stage5_start(api, peer_id, cmid, user, db)
        elif action == "stage5_next_substep":
            from vk_handlers.practices_stage5 import vk_handle_stage5_next
            await vk_handle_stage5_next(api, peer_id, cmid, user, db)
        elif action == "stage5_prev_substep":
            from vk_handlers.practices_stage5 import vk_handle_stage5_prev
            await vk_handle_stage5_prev(api, peer_id, cmid, user, db)

        # --- Stage 6 ---
        elif action == "start_stage6_finale":
            await _handle_start_stage6_finale(api, peer_id, cmid, user, db)

        # --- Всходы ---
        elif action == "sprouts_appeared":
            await _handle_sprouts_appeared(api, peer_id, cmid, user, db)

        # --- Продолжение ---
        elif action == "continue_practice":
            await _handle_continue_practice(api, peer_id, cmid, user, db)

        # --- Сброс ---
        elif action == "confirm_reset":
            await _handle_confirm_reset(api, peer_id, cmid, user, db)
        elif action == "cancel_reset":
            await _handle_cancel_reset(api, peer_id, cmid, user, db)
        elif action == "start_practice_after_reset":
            await _handle_start_practice_after_reset(api, peer_id, cmid, user, db)

        # --- Часовой пояс и время (Stage 1) ---
        elif action.startswith("stage1_tz_"):
            await _handle_stage1_timezone(api, peer_id, cmid, user, db, action)
        elif action.startswith("stage1_time_"):
            await _handle_stage1_time(api, peer_id, cmid, user, db, action)

        # --- Пересев ---
        elif action == "replant_start":
            await _handle_replant_step(api, peer_id, cmid, user, db, 1)
        elif action.startswith("replant_step_"):
            step_id = int(action.split("_")[-1])
            await _handle_replant_step(api, peer_id, cmid, user, db, step_id)
        elif action == "replant_complete":
            await _handle_replant_complete(api, peer_id, cmid, user, db)

        # --- Плесень ---
        elif action == "mold_start":
            await _handle_mold_start(api, peer_id, cmid, user, db)
        elif action == "mold_complete":
            await _handle_mold_complete(api, peer_id, cmid, user, db)
        elif action == "mold_sprouts_start":
            await _handle_mold_sprouts_start(api, peer_id, cmid, user, db)
        elif action == "mold_sprouts_complete":
            await _handle_mold_sprouts_complete(api, peer_id, cmid, user, db)

        # --- Всё погибло ---
        elif action.startswith("all_dead_step_"):
            step_id = int(action.split("_")[-1])
            await _handle_all_dead_step(api, peer_id, cmid, user, db, step_id)
        elif action == "all_dead_complete":
            await _handle_all_dead_complete(api, peer_id, cmid, user, db)

        else:
            await _edit(api, peer_id, cmid,
                        f"Действие '{action}' пока не реализовано. 🌱")
            logger.warning(f"[VK] Неизвестное действие: {action}")

    except Exception as e:
        logger.error(f"[VK] Ошибка в practice callback: {e}", exc_info=True)
    finally:
        db.close()


# ==================== НАВИГАЦИЯ ПО ШАГАМ ====================

async def _handle_next_step(api, peer_id, cmid, user, db):
    """Перейти к следующему шагу"""
    current_stage = user.current_stage
    current_step = user.current_step

    stage = practices_manager.get_stage(current_stage)
    if not stage:
        await _edit(api, peer_id, cmid, "Ошибка: этап не найден")
        return

    next_step_id = current_step + 1
    next_step = None
    for step in stage.get('steps', []):
        if step.get('step_id') == next_step_id:
            next_step = step
            break

    if next_step:
        update_user_progress_obj(db, user, stage_id=current_stage, step_id=next_step_id, day=user.current_day)

        message = _step_message(next_step)
        buttons = next_step.get('buttons', [])
        keyboard = _practice_kb(buttons) if buttons else None

        await _edit(api, peer_id, cmid, message, keyboard)
        logger.info(f"[VK] Пользователь {user.vk_id} перешел на шаг {next_step_id} этапа {current_stage}")
    else:
        await _edit(api, peer_id, cmid,
                    f"Этап {current_stage} завершен! 🎉\n\n"
                    f"Следующий этап будет доступен позже.\n"
                    f"Напиши 'Статус' чтобы увидеть прогресс.")


async def _handle_prev_step(api, peer_id, cmid, user, db):
    """Вернуться к предыдущему шагу"""
    current_stage = user.current_stage
    current_step = user.current_step

    if current_step <= 1:
        return

    stage = practices_manager.get_stage(current_stage)
    if not stage:
        await _edit(api, peer_id, cmid, "Ошибка: этап не найден")
        return

    prev_step_id = current_step - 1
    prev_step = None
    for step in stage.get('steps', []):
        if step.get('step_id') == prev_step_id:
            prev_step = step
            break

    if prev_step:
        update_user_progress_obj(db, user, stage_id=current_stage, step_id=prev_step_id, day=user.current_day)

        message = _step_message(prev_step)
        buttons = prev_step.get('buttons', [])
        keyboard = _practice_kb(buttons) if buttons else None

        await _edit(api, peer_id, cmid, message, keyboard)
        logger.info(f"[VK] Пользователь {user.vk_id} вернулся на шаг {prev_step_id} этапа {current_stage}")


async def _handle_complete_stage(api, peer_id, cmid, user, db):
    """Завершить текущий этап"""
    current_stage = user.current_stage

    # Этап 1: настройка часового пояса
    if current_stage == 1:
        user.awaiting_sprouts = True
        db.commit()

        keyboard = create_vk_callback_keyboard([
            ("🇷🇺 Москва (UTC+3)", "stage1_tz_Europe/Moscow"),
            ("🇷🇺 Самара (UTC+4)", "stage1_tz_Europe/Samara"),
            ("🇷🇺 Екатеринбург (UTC+5)", "stage1_tz_Asia/Yekaterinburg"),
            ("🇷🇺 Новосибирск (UTC+7)", "stage1_tz_Asia/Novosibirsk"),
            ("🇷🇺 Владивосток (UTC+10)", "stage1_tz_Asia/Vladivostok"),
        ])

        await _edit(api, peer_id, cmid,
                    "🌍 Настройка часового пояса\n\n"
                    "Прежде чем продолжить, давай настроим напоминания!\n\n"
                    "Выбери свой часовой пояс:",
                    keyboard)
        return

    # Этап 2: переход к ежедневным практикам
    if current_stage == 2:
        update_user_progress_obj(db, user, stage_id=3, step_id=0, day=user.current_day)

        user.awaiting_sprouts = False
        user.last_reminder_sent = datetime.utcnow()
        db.commit()

        stage = practices_manager.get_stage(3)
        if stage:
            steps = stage.get('steps', [])
            transition_step = None
            for step in steps:
                if step.get('step_id') == 0:
                    transition_step = step
                    break

            if transition_step:
                message = _step_message(transition_step)
                buttons = transition_step.get('buttons', [])
                keyboard = _practice_kb(buttons) if buttons else None
                await _edit(api, peer_id, cmid, message, keyboard)
                return

        await _edit(api, peer_id, cmid, "Ошибка: переходное сообщение этапа 3 не найдено")
        return

    # Переход к следующему этапу
    next_stage = current_stage + 1
    stage = practices_manager.get_stage(next_stage)

    if stage:
        update_user_progress_obj(db, user, stage_id=next_stage, step_id=1, day=user.current_day)

        await _edit(api, peer_id, cmid,
                    f"🎉 Этап {current_stage} завершён!\n\n"
                    f"Переходим к этапу {next_stage}: {stage.get('stage_name', '')}\n\n"
                    f"Напиши 'Статус' чтобы увидеть прогресс.")
    else:
        user.current_stage = 7
        db.commit()

        await _edit(api, peer_id, cmid,
                    "🎊 ПОЗДРАВЛЯЕМ! 🎊\n\n"
                    "Вы завершили все практики предвкушения!\n\n"
                    "Вы прошли путь от семечка до урожая. 🌱")


# ==================== STAGE 1 TIMEZONE/TIME ====================

async def _handle_stage1_timezone(api, peer_id, cmid, user, db, action):
    """Выбор часового пояса после Stage 1"""
    timezone_str = action.replace("stage1_tz_", "")
    user.timezone = timezone_str
    db.commit()

    keyboard = create_vk_callback_keyboard([
        ("09:00", "stage1_time_09:00"),
        ("10:00", "stage1_time_10:00"),
        ("11:00", "stage1_time_11:00"),
        ("12:00", "stage1_time_12:00"),
        ("13:00", "stage1_time_13:00"),
        ("14:00", "stage1_time_14:00"),
        ("18:00", "stage1_time_18:00"),
        ("19:00", "stage1_time_19:00"),
        ("20:00", "stage1_time_20:00"),
        ("21:00", "stage1_time_21:00"),
    ], cols=5)

    await _edit(api, peer_id, cmid,
                f"⏰ Настройка времени напоминаний\n\n"
                f"Часовой пояс: {timezone_str} ✓\n\n"
                f"Теперь выбери время для напоминаний:",
                keyboard)


async def _handle_stage1_time(api, peer_id, cmid, user, db, action):
    """Выбор времени после Stage 1"""
    time_str = action.replace("stage1_time_", "")

    user.preferred_time = time_str
    user.last_reminder_sent = datetime.utcnow()
    db.commit()

    keyboard = create_vk_callback_keyboard([
        ("🌱 Появились первые всходы!", "sprouts_appeared"),
    ])

    await _edit(api, peer_id, cmid,
                f"🎉 Этап 1 завершён!\n\n"
                f"Отличная работа! Семена посажены.\n\n"
                f"⏰ Напоминания настроены: {time_str} ({user.timezone})\n\n"
                f"Обычно первые всходы появляются через 2-4 дня.\n\n"
                f"💡 Что делать:\n"
                f"• Проверяй горшок каждый день\n"
                f"• Следи за влажностью почвы\n"
                f"• Держи горшок под крышкой\n\n"
                f"Как только увидишь первые зелёные петельки — нажми кнопку! 🌱\n\n"
                f"Я буду присылать напоминания проверить всходы.",
                keyboard)


# ==================== ВСХОДЫ ====================

async def _handle_sprouts_appeared(api, peer_id, cmid, user, db):
    """Всходы появились"""
    if user.current_stage != 1:
        await _edit(api, peer_id, cmid,
                    "Эта функция доступна только на Этапе 1 (после посадки).\n\n"
                    "Напиши 'Статус' для проверки прогресса.")
        return

    user.awaiting_sprouts = False
    db.commit()

    update_user_progress_obj(db, user, stage_id=2, step_id=7, day=2)

    stage2 = practices_manager.get_stage(2)
    if not stage2:
        await _edit(api, peer_id, cmid, "Ошибка: не найден Этап 2")
        return

    first_step = stage2['steps'][0]

    message = "🎉 Отлично! Ваши всходы появились!\n\n"
    message += _step_message(first_step)

    buttons = first_step.get('buttons', [])
    keyboard = _practice_kb(buttons) if buttons else None

    await _edit(api, peer_id, cmid, message, keyboard)
    logger.info(f"[VK] Пользователь {user.vk_id} подтвердил всходы, переведён на Этап 2")


# ==================== ПРИМЕРЫ ====================

async def _handle_show_examples(api, peer_id, cmid, user, db, vk_user_id=None):
    """Показать примеры желаний с аккордеоном"""
    opened = set()
    if vk_user_id:
        state = _user_state.get(vk_user_id, {})
        opened = state.get('opened_categories', set())

    examples = practices_manager.get_examples_menu()

    message = f"{examples.get('title', 'Примеры желаний')}\n\n"
    message += examples.get('message', '') + "\n\n"

    categories = examples.get('categories', [])
    buttons = []

    for category in categories:
        cat_id = category.get('id', '')
        is_open = cat_id in opened

        arrow = "🔽" if is_open else "▶️"
        buttons.append((f"{arrow} {category.get('title', '')}", f"toggle_category_{cat_id}"))

        if is_open:
            message += f"\n{category.get('title', '')}\n"
            message += f"{category.get('description', '')}\n\n"
            for item in category.get('items', []):
                message += f"• {item}\n"
            message += "\n"

    buttons.append(("✅ Продолжить практику", "continue_from_examples"))

    keyboard = create_vk_callback_keyboard(buttons)
    await _edit(api, peer_id, cmid, markdown_to_plain(message), keyboard)


# ==================== РЕЦЕПТЫ ====================

async def _handle_show_recipes(api, peer_id, cmid, user, db, vk_user_id=None):
    """Показать рецепты с аккордеоном"""
    opened = set()
    if vk_user_id:
        state = _user_state.get(vk_user_id, {})
        opened = state.get('opened_recipes', set())

    recipes = practices_manager.get_recipes()

    message = f"{recipes.get('title', 'Рецепты')} 🍽\n\n"
    message += recipes.get('message', '')

    items = recipes.get('items', [])

    for recipe in items:
        recipe_id = recipe.get('id', '')
        if recipe_id in opened:
            message += f"\n\n{recipe.get('title', '')}\n"
            message += f"{recipe.get('subtitle', '')}\n\n"
            message += f"Ингредиенты: {recipe.get('ingredients', '')}\n"
            message += f"Как делать: {recipe.get('instructions', '')}\n"
            if recipe.get('secret'):
                message += f"В чём секрет: {recipe.get('secret')}\n"
            if recipe.get('meaning'):
                message += f"Смысл: {recipe.get('meaning')}\n"

    buttons = []
    for recipe in items:
        recipe_id = recipe.get('id', '')
        title = recipe.get('title', '')
        if recipe_id in opened:
            buttons.append((f"▼ {title}", f"collapse_recipe_{recipe_id}"))
        else:
            buttons.append((title, f"expand_recipe_{recipe_id}"))

    if user.current_stage == 4:
        buttons.append(("✅ Продолжить", "next_step"))
    else:
        buttons.append(("✅ Завершить практику", "next_daily_substep"))

    keyboard = create_vk_callback_keyboard(buttons)
    await _edit(api, peer_id, cmid, markdown_to_plain(message), keyboard)


# ==================== МАНИФЕСТ ====================

async def _handle_show_manifesto(api, peer_id, cmid, user, db):
    """Показать манифест"""
    manifesto = practices_manager.get_manifesto()

    message = f"{manifesto.get('title', 'Манифест')}\n\n"
    message += manifesto.get('message', '') + "\n\n"

    for principle in manifesto.get('principles', []):
        message += f"\n{principle.get('number')}.\n{principle.get('text', '')}\n"

    message += f"\n\n{manifesto.get('closing', '')}"

    await _edit(api, peer_id, cmid, markdown_to_plain(message))


# ==================== ЕЖЕДНЕВНЫЕ ПРАКТИКИ STAGE 3 ====================

async def _handle_start_waiting_for_daily(api, peer_id, cmid, user, db):
    """Начать ожидание ежедневных практик"""
    user.daily_practice_day = 0
    db.commit()

    await _edit(api, peer_id, cmid,
                "✅ Отлично! Я буду присылать напоминания о практиках.\n\n"
                "Первое напоминание придёт в твоё предпочтительное время.\n\n"
                "🌱 До встречи на практике!")


async def _handle_start_daily_substep(api, peer_id, cmid, user, db):
    """Начать подшаги дня Stage 3"""
    current_day = user.daily_practice_day

    stage = practices_manager.get_stage(3)
    if not stage:
        await _edit(api, peer_id, cmid, "Ошибка: этап не найден")
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)
    if not daily_practice:
        await _edit(api, peer_id, cmid, f"Ошибка: практика дня {current_day} не найдена")
        return

    user.daily_practice_substep = "intro"
    db.commit()

    substep = _get_substep_by_id(daily_practice, "intro")
    if not substep:
        await _edit(api, peer_id, cmid, "Ошибка: подшаг не найден")
        return

    await _send_substep_message_vk(api, peer_id, cmid, substep)


async def _handle_next_daily_substep(api, peer_id, cmid, user, db):
    """Переход к следующему подшагу Stage 3"""
    current_day = user.daily_practice_day
    current_substep = user.daily_practice_substep

    stage = practices_manager.get_stage(3)
    if not stage:
        await _edit(api, peer_id, cmid, "Ошибка: этап не найден")
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)
    if not daily_practice:
        await _edit(api, peer_id, cmid, f"Ошибка: практика дня {current_day} не найдена")
        return

    next_substep_id = _get_next_substep_id(current_substep)
    substep = _get_substep_by_id(daily_practice, next_substep_id)

    # Если после practice есть practice2
    if current_substep == "practice":
        practice2_substep = _get_substep_by_id(daily_practice, "practice2")
        if practice2_substep:
            next_substep_id = "practice2"
            substep = practice2_substep

    if not substep:
        await _edit(api, peer_id, cmid, "Ошибка: подшаг не найден")
        return

    user.daily_practice_substep = next_substep_id
    db.commit()

    # Авто-переходы
    if substep.get('auto_proceed'):
        await _send_substep_message_vk(api, peer_id, cmid, substep)
        await asyncio.sleep(3)
        await _handle_next_daily_substep(api, peer_id, cmid, user, db)
        return

    if substep.get('auto_complete'):
        await _complete_daily_practice_flow(api, peer_id, cmid, user, db, substep)
        return

    await _send_substep_message_vk(api, peer_id, cmid, substep)


async def _handle_prev_daily_substep(api, peer_id, cmid, user, db):
    """Вернуться к предыдущему подшагу Stage 3"""
    current_substep = user.daily_practice_substep
    current_day = user.daily_practice_day

    back_flow = {
        "practice": "intro",
        "checkin": "practice",
        "response_A": "checkin",
        "response_B": "checkin",
    }

    prev_substep = back_flow.get(current_substep)
    if not prev_substep:
        return

    user.daily_practice_substep = prev_substep
    db.commit()

    stage = practices_manager.get_stage(3)
    if not stage:
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)
    if not daily_practice:
        return

    prev_substep_data = _get_substep_by_id(daily_practice, prev_substep)
    if not prev_substep_data:
        return

    await _send_substep_message_vk(api, peer_id, cmid, prev_substep_data)


async def _handle_daily_choice(api, peer_id, cmid, user, db, choice_substep):
    """Выбор кнопки A или B в check-in Stage 3"""
    user.daily_practice_substep = choice_substep
    db.commit()

    current_day = user.daily_practice_day
    stage = practices_manager.get_stage(3)
    if not stage:
        return

    daily_practice = _get_daily_practice_by_day(stage, current_day)
    if not daily_practice:
        return

    substep = _get_substep_by_id(daily_practice, choice_substep)
    if not substep:
        return

    await _send_substep_message_vk(api, peer_id, cmid, substep)


async def _complete_daily_practice_flow(api, peer_id, cmid, user, db, final_substep):
    """Завершить флоу ежедневной практики Stage 3"""
    current_day = user.daily_practice_day

    message = markdown_to_plain(final_substep.get('message', ''))
    await _edit(api, peer_id, cmid, message)

    if current_day >= 4:
        # Переход к Stage 4
        update_user_progress_obj(db, user, stage_id=4, step_id=12, day=user.current_day)
        user.daily_practice_day = 0
        user.daily_practice_substep = ""
        user.last_practice_date = None
        user.reminder_postponed = False
        user.postponed_until = None

        tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        user.stage4_reminder_date = tomorrow
        db.commit()
        return

    # Обычное завершение дня
    user.daily_practice_day = current_day + 1
    user.daily_practice_substep = ""
    user.last_practice_date = date.today().strftime('%Y-%m-%d')
    user.reminder_postponed = False
    user.postponed_until = None
    db.commit()


async def _handle_complete_daily_practice(api, peer_id, cmid, user, db):
    """Завершить ежедневную практику"""
    current_day = user.daily_practice_day

    if current_day >= 4:
        update_user_progress_obj(db, user, stage_id=4, step_id=12, day=user.current_day)
        user.daily_practice_day = 0
        user.last_practice_date = None
        user.reminder_postponed = False
        user.postponed_until = None
        db.commit()

        await _edit(api, peer_id, cmid,
                    "🎉 Все 4 дня практик «Свидетель» завершены!\n\n"
                    "Отличная работа! Ты освоил(а) навык не-вмешательства.\n\n"
                    "Скоро мы перейдём к практике первого урожая!")
    else:
        user.daily_practice_day = current_day + 1
        user.last_practice_date = date.today().strftime('%Y-%m-%d')
        user.reminder_postponed = False
        user.postponed_until = None
        db.commit()

        await _edit(api, peer_id, cmid,
                    f"✅ Практика дня {current_day} завершена!\n\n"
                    f"Молодец! Ты сделал(а) ещё один шаг.\n\n"
                    f"До встречи завтра! 🌱")


async def _handle_complete_day4_practice(api, peer_id, cmid, user, db):
    """Завершить практику дня 4"""
    await _complete_daily_practice_flow(api, peer_id, cmid, user, db, {
        "message": "✅ Практика дня 4 завершена!\n\n🌱 Жди напоминание о следующей практике."
    })


async def _handle_postpone_reminder(api, peer_id, cmid, user, db):
    """Отложить напоминание на 2 часа"""
    postponed_time = datetime.now() + timedelta(hours=2)
    user.reminder_postponed = True
    user.postponed_until = postponed_time
    db.commit()

    await _edit(api, peer_id, cmid,
                f"⏰ Напоминание отложено\n\n"
                f"Я напомню о практике через 2 часа.\n\n"
                f"Время напоминания: {postponed_time.strftime('%H:%M')}\n\n"
                f"До встречи! 🌱")


async def _handle_view_daily_practice(api, peer_id, cmid, user, db):
    """Показать текущую ежедневную практику"""
    current_day = user.daily_practice_day

    stage = practices_manager.get_stage(3)
    if not stage:
        await _edit(api, peer_id, cmid, "Ошибка: этап 3 не найден")
        return

    practice = _get_daily_practice_by_day(stage, current_day)
    if not practice:
        await _edit(api, peer_id, cmid, f"Ошибка: практика дня {current_day} не найдена")
        return

    message = _step_message(practice)
    buttons = practice.get('buttons', [])
    keyboard = _practice_kb(buttons) if buttons else None

    await _edit(api, peer_id, cmid, message, keyboard)


# ==================== STAGE 5 START ====================

async def _handle_start_daily_practices(api, peer_id, cmid, user, db):
    """Начать Stage 5 ежедневные практики"""
    update_user_progress_obj(db, user, stage_id=5, step_id=17, day=user.current_day)

    user.daily_practice_day = 0
    user.daily_practice_substep = ""
    user.last_practice_date = None
    user.reminder_postponed = False
    user.postponed_until = None
    db.commit()

    await _edit(api, peer_id, cmid,
                "✅ Отлично! Начинаем новый цикл.\n\n"
                "Следующие 7 дней ты будешь получать ежедневные практики.\n\n"
                "Каждый день — новая тема для работы с долгосрочными целями.\n\n"
                "🌱 Первое напоминание придет завтра!")


# ==================== STAGE 6 ====================

async def _handle_start_stage6_finale(api, peer_id, cmid, user, db):
    """Начать финальные практики Stage 6"""
    if user.current_stage != 6:
        update_user_progress_obj(db, user, stage_id=6, step_id=24, day=user.current_day)

    stage = practices_manager.get_stage(6)
    if not stage:
        await _edit(api, peer_id, cmid, "Ошибка: Stage 6 не найден")
        return

    step = None
    for s in stage.get('steps', []):
        if s.get('step_id') == 24:
            step = s
            break

    if not step:
        await _edit(api, peer_id, cmid, "Ошибка: Step 24 не найден")
        return

    message = _step_message(step)
    buttons = step.get('buttons', [])
    keyboard = _practice_kb(buttons) if buttons else None

    await _edit(api, peer_id, cmid, message, keyboard)


# ==================== ПРОДОЛЖЕНИЕ ПРАКТИКИ ====================

async def _handle_continue_practice(api, peer_id, cmid, user, db):
    """Продолжить практику с текущего шага"""
    current_stage = user.current_stage
    current_step_id = user.current_step

    stage = practices_manager.get_stage(current_stage)
    if not stage:
        await _edit(api, peer_id, cmid,
                    f"❌ Не удалось найти Этап {current_stage}\n\n"
                    "Напишите 'Меню' для помощи.")
        return

    step = practices_manager.get_step(stage_id=current_stage, step_id=current_step_id)

    if not step:
        steps = stage.get('steps', [])
        if steps:
            step = steps[0]
            user.current_step = step.get('step_id')
            db.commit()
        else:
            await _edit(api, peer_id, cmid, f"❌ Этап {current_stage} не содержит практик")
            return

    message = _step_message(step)
    buttons = step.get('buttons', [])
    keyboard = _practice_kb(buttons) if buttons else None

    await _edit(api, peer_id, cmid, message, keyboard)


# ==================== СБРОС ====================

async def _handle_confirm_reset(api, peer_id, cmid, user, db):
    """Подтвердить сброс"""
    reset_user_progress_obj(db, user)

    first_step = practices_manager.get_step(stage_id=1, step_id=1)
    if not first_step:
        await _edit(api, peer_id, cmid, "😞 Ошибка при загрузке практик.")
        return

    update_user_progress_obj(db, user, stage_id=1, step_id=1, day=1)

    user.started_at = datetime.utcnow()
    db.commit()

    message = "🔄 Прогресс сброшен!\n\n"
    message += "Начнём сначала! 🌱\n\n"
    message += _step_message(first_step)

    buttons = first_step.get('buttons', [])
    keyboard = _practice_kb(buttons) if buttons else None

    await _edit(api, peer_id, cmid, message, keyboard)


async def _handle_cancel_reset(api, peer_id, cmid, user, db):
    """Отменить сброс"""
    current_stage = user.current_stage
    step = practices_manager.get_step(stage_id=current_stage, step_id=user.current_step)

    if not step:
        stage = practices_manager.get_stage(current_stage)
        if stage and stage.get('steps'):
            step = stage['steps'][0]
            user.current_step = step.get('step_id')
            db.commit()

    if step:
        message = "✅ Сброс отменён!\n\nВозвращаемся к практике:\n\n"
        message += _step_message(step)
        buttons = step.get('buttons', [])
        keyboard = _practice_kb(buttons) if buttons else None
        await _edit(api, peer_id, cmid, message, keyboard)
    else:
        await _edit(api, peer_id, cmid,
                    "✅ Сброс отменён.\n\nНапишите 'Статус' для проверки прогресса.")


async def _handle_start_practice_after_reset(api, peer_id, cmid, user, db):
    """Начать практику после сброса"""
    first_step = practices_manager.get_step(stage_id=1, step_id=1)
    if not first_step:
        await _edit(api, peer_id, cmid, "😞 Ошибка при загрузке практик.")
        return

    update_user_progress_obj(db, user, stage_id=1, step_id=1, day=1)

    user.started_at = datetime.utcnow()
    db.commit()

    message = _step_message(first_step)
    buttons = first_step.get('buttons', [])
    keyboard = _practice_kb(buttons) if buttons else None

    await _edit(api, peer_id, cmid, message, keyboard)


# ==================== ПЕРЕСЕВ ====================

async def _handle_replant_step(api, peer_id, cmid, user, db, step_id: int):
    """Показать шаг сценария 'Салат не взошёл'"""
    replant = practices_manager.get_replant_scenario()
    if not replant:
        await _edit(api, peer_id, cmid, "Ошибка: сценарий не найден")
        return

    step = None
    for s in replant.get('steps', []):
        if s.get('step_id') == step_id:
            step = s
            break

    if not step:
        await _edit(api, peer_id, cmid, f"Ошибка: шаг {step_id} не найден")
        return

    message = _step_message(step)
    keyboard = _practice_kb(step.get('buttons', []))

    await _edit(api, peer_id, cmid, message, keyboard)


async def _handle_replant_complete(api, peer_id, cmid, user, db):
    """Завершить пересев"""
    user.awaiting_sprouts = True
    user.started_at = datetime.utcnow()
    db.commit()

    keyboard = create_vk_callback_keyboard([
        ("✅ Всходы появились!", "sprouts_appeared"),
    ])

    await _edit(api, peer_id, cmid,
                "🌱 Семена посажены заново!\n\n"
                "Таймер сброшен. Жди новых всходов — обычно 2-4 дня.\n\n"
                "Я буду присылать напоминания проверить горшок.\n\n"
                "Как только увидишь первые зелёные петельки — нажми кнопку! 🌱",
                keyboard)


# ==================== ПЛЕСЕНЬ ====================

async def _handle_mold_start(api, peer_id, cmid, user, db):
    """Плесень — показать инструкцию"""
    mold = practices_manager.get_mold_scenario()
    if not mold:
        await _edit(api, peer_id, cmid, "Ошибка: сценарий не найден")
        return

    message = _step_message(mold)
    keyboard = _practice_kb(mold.get('buttons', []))

    await _edit(api, peer_id, cmid, message, keyboard)


async def _handle_mold_complete(api, peer_id, cmid, user, db):
    """Завершить сценарий плесени (без сброса таймера)"""
    keyboard = create_vk_callback_keyboard([
        ("✅ Всходы появились!", "sprouts_appeared"),
        ("🍄 Плесень снова", "mold_start"),
    ])

    await _edit(api, peer_id, cmid,
                "🌱 Отлично!\n\n"
                "Ты справился(ась) с плесенью. Продолжай наблюдать за горшком.\n\n"
                "Как только увидишь первые зелёные петельки — нажми кнопку! 🌱",
                keyboard)


async def _handle_mold_sprouts_start(api, peer_id, cmid, user, db):
    """Плесень на ростках (Stage 3-5)"""
    mold = practices_manager.get_mold_sprouts_scenario()
    if not mold:
        await _edit(api, peer_id, cmid, "Ошибка: сценарий не найден")
        return

    message = _step_message(mold)
    keyboard = _practice_kb(mold.get('buttons', []))

    await _edit(api, peer_id, cmid, message, keyboard)


async def _handle_mold_sprouts_complete(api, peer_id, cmid, user, db):
    """Завершить плесень на ростках"""
    current_stage = user.current_stage
    current_day = user.daily_practice_day or 1

    if current_stage == 3:
        stage = practices_manager.get_stage(3)
        if stage:
            daily_practice = _get_daily_practice_by_day(stage, current_day)
            if daily_practice:
                reminder = daily_practice.get('reminder', {})
                message = reminder.get('message', '')
                buttons = reminder.get('buttons', [])
                btn_list = [(b['text'], b['action']) for b in buttons if b.get('text') and b.get('action')]
                btn_list.append(("🍄 Плесень", "mold_sprouts_start"))
                keyboard = create_vk_callback_keyboard(btn_list)
                await _edit(api, peer_id, cmid,
                            f"🌱 Отлично! Ты справился(ась) с плесенью.\n\n{markdown_to_plain(message)}",
                            keyboard)
                return

    elif current_stage == 4:
        stage = practices_manager.get_stage(4)
        if stage:
            steps = stage.get('steps', [])
            if steps:
                first_step = steps[0]
                message = "🌱 Отлично! Ты справился(ась) с плесенью.\n\n"
                message += _step_message(first_step)
                buttons_data = first_step.get('buttons', [])
                btn_list = [(b['text'], b['action']) for b in buttons_data if b.get('text') and b.get('action')]
                if not btn_list:
                    btn_list.append(("Начать практику", "next_step"))
                btn_list.append(("🍄 Плесень", "mold_sprouts_start"))
                keyboard = create_vk_callback_keyboard(btn_list)
                await _edit(api, peer_id, cmid, message, keyboard)
                return

    elif current_stage == 5:
        stage = practices_manager.get_stage(5)
        if stage:
            for p in stage.get('daily_practices', []):
                if p.get('day') == current_day:
                    theme = p.get('theme', '')
                    message = (
                        f"🌱 Отлично! Ты справился(ась) с плесенью.\n\n"
                        f"День {current_day} из 7: {theme}\n\n"
                        f"Пришло время ежедневной практики."
                    )
                    keyboard = create_vk_callback_keyboard([
                        ("Начать практику", "stage5_start_substep"),
                        ("Напомнить позже", "postpone_reminder"),
                        ("🍄 Плесень", "mold_sprouts_start"),
                    ])
                    await _edit(api, peer_id, cmid, message, keyboard)
                    return

    # Fallback
    keyboard = create_vk_callback_keyboard([
        ("Продолжить практику", "continue_practice"),
    ])
    await _edit(api, peer_id, cmid,
                "🌱 Отлично!\n\n"
                "Ты справился(ась) с плесенью. Возвращайся к практике!",
                keyboard)


# ==================== ВСЁ ПОГИБЛО ====================

async def _handle_all_dead_step(api, peer_id, cmid, user, db, step_id: int):
    """Показать шаг сценария 'Всё погибло'"""
    all_dead = practices_manager.get_all_dead_scenario()
    if not all_dead:
        await _edit(api, peer_id, cmid, "Ошибка: сценарий не найден")
        return

    step = None
    for s in all_dead.get('steps', []):
        if s.get('step_id') == step_id:
            step = s
            break

    if not step:
        await _edit(api, peer_id, cmid, f"Ошибка: шаг {step_id} не найден")
        return

    message = _step_message(step)
    keyboard = _practice_kb(step.get('buttons', []))

    await _edit(api, peer_id, cmid, message, keyboard)


async def _handle_all_dead_complete(api, peer_id, cmid, user, db):
    """Завершить 'Всё погибло' — сброс и ожидание всходов"""
    reset_user_progress_obj(db, user)
    update_user_progress_obj(db, user, stage_id=1, step_id=1, day=1)

    user.started_at = datetime.utcnow()
    user.awaiting_sprouts = True
    db.commit()

    keyboard = create_vk_callback_keyboard([
        ("✅ Появились первые всходы", "sprouts_appeared"),
    ])

    await _edit(api, peer_id, cmid,
                "🌱 Жди уведомлений о всходах, удачи!\n\n"
                "Я буду присылать напоминания проверить горшок.\n"
                "Как только увидишь первые зелёные петельки — нажми кнопку!",
                keyboard)
