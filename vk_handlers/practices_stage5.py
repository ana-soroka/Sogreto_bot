"""
VK обработчики для Stage 5 (До беби-лифа) — ежедневные практики с долгосрочными целями
Порт handlers/practices_stage5.py для ВКонтакте
"""
import logging
from datetime import date, timedelta

from utils import practices_manager
from utils.db import update_user_progress_obj
from utils.formatting import markdown_to_plain
from utils.vk_keyboards import create_vk_callback_keyboard

logger = logging.getLogger(__name__)


async def _edit(api, peer_id, cmid, message, keyboard=None):
    """Редактировать сообщение"""
    kwargs = {"peer_id": peer_id, "conversation_message_id": cmid, "message": message}
    if keyboard:
        kwargs["keyboard"] = keyboard
    await api.messages.edit(**kwargs)


def _get_stage5_daily_practice(day: int):
    """Получить практику дня для Stage 5"""
    stage = practices_manager.get_stage(5)
    if not stage:
        return None
    for practice in stage.get('daily_practices', []):
        if practice.get('day') == day:
            return practice
    return None


def _get_stage5_step_by_type(practice, step_type: str):
    """Получить подшаг практики по типу"""
    for step in practice.get('steps', []):
        if step.get('type') == step_type:
            return step
    return None


async def vk_handle_stage5_start(api, peer_id, cmid, user, db):
    """Начать подшаги Stage 5 (intro)"""
    current_day = user.daily_practice_day

    logger.info(f"[VK] Пользователь {user.vk_id} начинает подшаги Stage 5, день {current_day}")

    practice = _get_stage5_daily_practice(current_day)
    if not practice:
        await _edit(api, peer_id, cmid, "Ошибка: практика дня не найдена")
        return

    user.daily_practice_substep = "intro"
    db.commit()

    step = _get_stage5_step_by_type(practice, "intro")
    if not step:
        await _edit(api, peer_id, cmid, "Ошибка: подшаг не найден")
        return

    theme = practice.get('theme', '')
    message = f"🌱 День {current_day} из 7: {theme}\n\n"
    message += markdown_to_plain(step.get('text', ''))

    keyboard = create_vk_callback_keyboard([
        ("Продолжить", "stage5_next_substep")
    ])

    await _edit(api, peer_id, cmid, message, keyboard)


async def vk_handle_stage5_next(api, peer_id, cmid, user, db):
    """Переход к следующему подшагу Stage 5"""
    current_day = user.daily_practice_day
    current_substep = user.daily_practice_substep

    logger.info(f"[VK] Пользователь {user.vk_id} переходит от '{current_substep}' к следующему (Stage 5)")

    practice = _get_stage5_daily_practice(current_day)
    if not practice:
        await _edit(api, peer_id, cmid, "Ошибка: практика дня не найдена")
        return

    # Определить следующий подшаг
    flow = {"intro": "timer", "timer": "affirmation", "affirmation": "watering"}
    next_substep = flow.get(current_substep)

    if current_substep == "watering":
        # Последний подшаг — завершить день
        await _complete_stage5_day(api, peer_id, cmid, user, db, practice)
        return

    if not next_substep:
        await _edit(api, peer_id, cmid, "Ошибка: неизвестный подшаг")
        return

    user.daily_practice_substep = next_substep
    db.commit()

    step = _get_stage5_step_by_type(practice, next_substep)
    if not step:
        await _edit(api, peer_id, cmid, "Ошибка: подшаг не найден")
        return

    theme = practice.get('theme', '')
    message = f"🌱 День {current_day} из 7: {theme}\n\n"
    message += markdown_to_plain(step.get('text', ''))

    # Кнопки зависят от подшага
    if next_substep == "timer":
        # VK: нет WebApp, вместо этого текстовая кнопка
        keyboard = create_vk_callback_keyboard([
            ("← Назад", "stage5_prev_substep"),
            ("Минута прошла", "stage5_next_substep"),
        ])
    elif next_substep == "affirmation":
        button_text = "Принято. До завтра" if current_day < 7 else "Перейти к празднику зрелости"
        keyboard = create_vk_callback_keyboard([
            ("← Назад", "stage5_prev_substep"),
            (button_text, "stage5_next_substep"),
        ])
    elif next_substep == "watering":
        keyboard = create_vk_callback_keyboard([
            ("← Назад", "stage5_prev_substep"),
            ("Ага", "stage5_next_substep"),
        ])
    else:
        keyboard = create_vk_callback_keyboard([
            ("Продолжить", "stage5_next_substep"),
        ])

    await _edit(api, peer_id, cmid, message, keyboard)

    logger.info(f"[VK] Пользователь {user.vk_id} перешёл к подшагу '{next_substep}' (Stage 5)")


async def _complete_stage5_day(api, peer_id, cmid, user, db, practice):
    """Завершить день практики Stage 5"""
    current_day = user.daily_practice_day

    logger.info(f"[VK] Пользователь {user.vk_id} завершает день {current_day} (Stage 5)")

    if current_day >= 7:
        # Переход к Stage 6
        update_user_progress_obj(db, user, stage_id=6, step_id=24, day=user.current_day)

        tomorrow = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        user.stage6_reminder_date = tomorrow

        user.daily_practice_day = 0
        user.daily_practice_substep = ""
        user.last_practice_date = None
        user.reminder_postponed = False
        user.postponed_until = None
        db.commit()

        await _edit(api, peer_id, cmid,
                    "🎉 Все 7 дней практик завершены!\n\n"
                    "Отличная работа! Ты освоил(а) навык работы с долгосрочными целями.\n\n"
                    "Твой беби-лиф готов! Скоро мы перейдём к финальному этапу.")

        logger.info(f"[VK] Пользователь {user.vk_id} завершил Stage 5, переход к Stage 6")
        return

    # Обычное завершение дня
    user.daily_practice_day = current_day + 1
    user.daily_practice_substep = ""
    user.last_practice_date = date.today().strftime('%Y-%m-%d')
    user.reminder_postponed = False
    user.postponed_until = None
    db.commit()

    theme = practice.get('theme', '')
    await _edit(api, peer_id, cmid,
                f"✅ День {current_day} завершён!\n\n"
                f"Тема: {theme}\n\n"
                f"Молодец! Ты сделал(а) ещё один шаг в работе с долгосрочными целями.\n\n"
                f"🌱 До встречи завтра!")

    logger.info(f"[VK] Пользователь {user.vk_id} завершил день {current_day} (Stage 5)")


async def vk_handle_stage5_prev(api, peer_id, cmid, user, db):
    """Вернуться к предыдущему подшагу Stage 5"""
    current_substep = user.daily_practice_substep
    current_day = user.daily_practice_day

    back_flow = {
        "timer": "intro",
        "affirmation": "timer",
        "watering": "affirmation",
    }

    prev_substep = back_flow.get(current_substep)
    if not prev_substep:
        return  # Нельзя вернуться с intro

    user.daily_practice_substep = prev_substep
    db.commit()

    practice = _get_stage5_daily_practice(current_day)
    if not practice:
        await _edit(api, peer_id, cmid, "Ошибка: практика дня не найдена")
        return

    prev_step_data = _get_stage5_step_by_type(practice, prev_substep)
    if not prev_step_data:
        return

    theme = practice.get('theme', '')
    message = f"🌱 День {current_day} из 7: {theme}\n\n"
    message += markdown_to_plain(prev_step_data.get('text', ''))

    if prev_substep == "intro":
        keyboard = create_vk_callback_keyboard([
            ("Продолжить", "stage5_next_substep"),
        ])
    elif prev_substep == "timer":
        keyboard = create_vk_callback_keyboard([
            ("← Назад", "stage5_prev_substep"),
            ("Минута прошла", "stage5_next_substep"),
        ])
    elif prev_substep == "affirmation":
        button_text = "Принято. До завтра" if current_day < 7 else "Перейти к празднику зрелости"
        keyboard = create_vk_callback_keyboard([
            ("← Назад", "stage5_prev_substep"),
            (button_text, "stage5_next_substep"),
        ])
    else:
        keyboard = create_vk_callback_keyboard([
            ("Продолжить", "stage5_next_substep"),
        ])

    await _edit(api, peer_id, cmid, message, keyboard)

    logger.info(f"[VK] Пользователь {user.vk_id} вернулся к подшагу '{prev_substep}' (Stage 5)")
