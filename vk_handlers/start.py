"""
VK обработчики: приветствие и главное меню
"""
import logging
from models import SessionLocal, User
from utils.db import get_or_create_vk_user
from utils.formatting import markdown_to_plain
from utils.vk_keyboards import create_vk_callback_keyboard, create_vk_menu_keyboard, create_vk_inline_keyboard

logger = logging.getLogger(__name__)


def _get_vk_menu_keyboard():
    """Клавиатура главного меню (макс. 6 рядов в VK inline)"""
    return create_vk_callback_keyboard([
        ("▶️ Продолжить практику", "menu_continue"),
        ("⚠️ Что-то пошло не так", "menu_problem"),
        ("🔄 Начать заново", "menu_reset"),
        ("📊 Мой прогресс", "menu_status"),
        ("⏰ Время напоминаний", "menu_set_time"),
        ("🌍 Часовой пояс", "menu_timezone"),
        ("📞 Поддержка", "menu_contact"),
    ], cols=2)


async def _get_vk_user_info(api, user_id: int):
    """Получить имя VK-пользователя"""
    try:
        users = await api.users.get(user_ids=[user_id])
        if users:
            return users[0].first_name, users[0].last_name
    except Exception as e:
        logger.warning(f"[VK] Не удалось получить инфо о пользователе {user_id}: {e}")
    return None, None


async def _edit(api, peer_id, cmid, message, keyboard=None):
    """Редактировать сообщение"""
    kwargs = {"peer_id": peer_id, "conversation_message_id": cmid, "message": message}
    if keyboard:
        kwargs["keyboard"] = keyboard
    await api.messages.edit(**kwargs)


async def _send(api, peer_id, message, keyboard=None):
    """Отправить сообщение"""
    kwargs = {"peer_id": peer_id, "message": message, "random_id": 0}
    if keyboard:
        kwargs["keyboard"] = keyboard
    await api.messages.send(**kwargs)


# ==================== КОМАНДЫ ====================

async def vk_start_command(api, message):
    """Обработчик команды 'Начать'"""
    user_id = message.from_id
    first_name, last_name = await _get_vk_user_info(api, user_id)

    logger.info(f"[VK] Пользователь {user_id} запустил 'Начать'")

    db = SessionLocal()
    try:
        db_user = get_or_create_vk_user(db, vk_id=user_id, first_name=first_name, last_name=last_name)
        user_stage = db_user.current_stage
        user_step = db_user.current_step
    finally:
        db.close()

    welcome = (
        f"Привет, {first_name or 'друг'}! 🌱\n\n"
        "Я — твой проводник в мир практик предвкушения.\n\n"
        "Вместе мы будем выращивать кресс-салат и культивировать эмоцию предвкушения. "
        "Каждый день — новая практика, новое открытие.\n\n"
        "Готов(а) начать? 🌿"
    )

    if user_stage > 1 or user_step > 1:
        keyboard = create_vk_callback_keyboard([("Давай начнем 🌱", "start_show_status")])
    else:
        keyboard = create_vk_callback_keyboard([("Давай начнем 🌱", "start_practice_from_start")])

    await message.answer(welcome, keyboard=keyboard)

    # Постоянная кнопка Меню
    await _send(api, message.peer_id,
                "Используй кнопку Меню внизу для доступа к настройкам.",
                keyboard=create_vk_menu_keyboard())


async def vk_menu_command(api, message):
    """Показать главное меню"""
    await message.answer(
        "📋 Главное меню\n\nВыбери нужное действие:",
        keyboard=_get_vk_menu_keyboard()
    )


# ==================== START CALLBACKS ====================

async def vk_handle_start_callback(api, peer_id, user_id, cmid, action):
    """Обработчик callback'ов от кнопки приветствия"""

    if action == "start_show_status":
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(vk_id=user_id).first()
            if db_user:
                status_text = (
                    f"📊 Твой прогресс\n\n"
                    f"🌱 Этап: {db_user.current_stage} из 6\n"
                    f"📅 День: {db_user.current_day}\n"
                    f"👣 Шаг: {db_user.current_step}\n\n"
                    "Напиши 'Меню' чтобы продолжить практику"
                )
                await _edit(api, peer_id, cmid, status_text)
        finally:
            db.close()

    elif action == "start_practice_from_start":
        from utils import practices_manager
        from utils.db import update_user_progress_obj

        db = SessionLocal()
        try:
            first_name, last_name = await _get_vk_user_info(api, user_id)
            user = get_or_create_vk_user(db, vk_id=user_id, first_name=first_name, last_name=last_name)

            first_step = practices_manager.get_step(stage_id=1, step_id=1)
            if not first_step:
                await _edit(api, peer_id, cmid, "😞 Произошла ошибка при загрузке практик.")
                return

            update_user_progress_obj(db, user, stage_id=1, step_id=1, day=1)

            from datetime import datetime
            if not user.started_at:
                user.started_at = datetime.utcnow()
                db.commit()

            title = first_step.get('title', 'Начало практики')
            msg = first_step.get('message', '')
            message = f"{title}\n\n{markdown_to_plain(msg)}"

            buttons = first_step.get('buttons', [])
            keyboard = create_vk_inline_keyboard(buttons) if buttons else None

            await _edit(api, peer_id, cmid, message, keyboard)
        finally:
            db.close()


# ==================== MENU CALLBACKS ====================

async def vk_handle_menu_callback(api, peer_id, user_id, cmid, action):
    """Обработчик нажатий кнопок главного меню"""

    if action == "menu_continue":
        from vk_handlers.practices import vk_handle_practice_callback
        await vk_handle_practice_callback(api, peer_id, user_id, cmid, "continue_practice")

    elif action == "menu_reset":
        keyboard = create_vk_callback_keyboard([
            ("✅ Да, начать заново", "confirm_reset"),
            ("❌ Отмена", "cancel_reset"),
        ])
        await _send(api, peer_id,
                    "🔄 Сброс прогресса\n\n"
                    "Вы уверены, что хотите начать практики заново?\n"
                    "Весь текущий прогресс будет сброшен.",
                    keyboard=keyboard)

    elif action == "menu_status":
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(vk_id=user_id).first()
            if db_user:
                status_text = (
                    f"📊 Твой прогресс\n\n"
                    f"🌱 Этап: {db_user.current_stage} из 6\n"
                    f"📅 День: {db_user.current_day}\n"
                    f"👣 Шаг: {db_user.current_step}\n"
                    f"⏸ Статус: {'На паузе' if db_user.is_paused else 'Активно'}"
                )
                await _send(api, peer_id, status_text)
            else:
                await _send(api, peer_id, "Вы ещё не начали практики. Напишите 'Начать'")
        finally:
            db.close()

    elif action == "menu_set_time":
        from vk_handlers.settings import vk_show_time_selection
        await vk_show_time_selection(api, peer_id)

    elif action == "menu_timezone":
        from vk_handlers.settings import vk_show_timezone_selection
        await vk_show_timezone_selection(api, peer_id)

    elif action == "menu_contact":
        await _send(api, peer_id,
                    "📞 Поддержка\n\n"
                    "По всем вопросам пишите:\n"
                    "💬 Telegram: @sogreto_support\n\n"
                    "Мы ответим в течение 24 часов.")

    elif action == "menu_problem":
        keyboard = create_vk_callback_keyboard([
            ("🍄 Плесень", "menu_mold"),
            ("💀 Всё погибло", "menu_all_dead"),
        ])
        await _send(api, peer_id,
                    "⚠️ Что-то пошло не так?\n\nВыбери, что случилось:",
                    keyboard=keyboard)

    elif action == "menu_mold":
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(vk_id=user_id).first()
            if not db_user:
                await _send(api, peer_id, "Вы ещё не начали практики. Напишите 'Начать'")
                return
            if db_user.current_stage <= 2:
                from vk_handlers.practices import vk_handle_practice_callback
                await vk_handle_practice_callback(api, peer_id, user_id, cmid, "mold_start")
            else:
                from vk_handlers.practices import vk_handle_practice_callback
                await vk_handle_practice_callback(api, peer_id, user_id, cmid, "mold_sprouts_start")
        finally:
            db.close()

    elif action == "menu_all_dead":
        keyboard = create_vk_callback_keyboard([
            ("✅ Да, начать посев заново", "menu_confirm_dead"),
            ("❌ Отмена", "menu_cancel_dead"),
        ])
        await _send(api, peer_id,
                    "💀 Всё погибло?\n\n"
                    "Не переживай, такое бывает! Мы начнём посев заново.\n\n"
                    "Прогресс будет сброшен, и ты пройдёшь цикл посева с начала.\n"
                    "После посева снова начнут приходить напоминания о всходах.",
                    keyboard=keyboard)

    elif action == "menu_confirm_dead":
        from vk_handlers.practices import vk_handle_practice_callback
        # Используем _send для нового сообщения, а callback роутим через practices
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(vk_id=user_id).first()
            if not db_user:
                await _send(api, peer_id, "Ошибка: пользователь не найден")
                return
            from vk_handlers.practices import _handle_all_dead_step
            await _handle_all_dead_step(api, peer_id, cmid, db_user, db, 1)
        finally:
            db.close()

    elif action == "menu_cancel_dead":
        await _send(api, peer_id,
                    "📋 Главное меню\n\nВыбери нужное действие:",
                    keyboard=_get_vk_menu_keyboard())
