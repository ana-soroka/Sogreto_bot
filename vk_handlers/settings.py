"""
VK обработчики: настройки времени и часового пояса
"""
import logging
from datetime import datetime
from models import SessionLocal, User
from utils.db import get_or_create_vk_user
from utils.vk_keyboards import create_vk_callback_keyboard

logger = logging.getLogger(__name__)


async def _send(api, peer_id, message, keyboard=None):
    """Отправить сообщение"""
    kwargs = {"peer_id": peer_id, "message": message, "random_id": 0}
    if keyboard:
        kwargs["keyboard"] = keyboard
    await api.messages.send(**kwargs)


async def _edit(api, peer_id, cmid, message, keyboard=None):
    """Редактировать сообщение"""
    kwargs = {"peer_id": peer_id, "conversation_message_id": cmid, "message": message}
    if keyboard:
        kwargs["keyboard"] = keyboard
    await api.messages.edit(**kwargs)


async def vk_show_time_selection(api, peer_id):
    """Показать выбор времени напоминаний"""
    keyboard = create_vk_callback_keyboard([
        ("09:00", "time_09:00"),
        ("10:00", "time_10:00"),
        ("11:00", "time_11:00"),
        ("12:00", "time_12:00"),
        ("13:00", "time_13:00"),
        ("14:00", "time_14:00"),
        ("18:00", "time_18:00"),
        ("19:00", "time_19:00"),
        ("20:00", "time_20:00"),
    ])
    await _send(api, peer_id,
                "⏰ Время напоминаний\n\nВыберите удобное время:",
                keyboard=keyboard)


async def vk_show_timezone_selection(api, peer_id):
    """Показать выбор часового пояса"""
    keyboard = create_vk_callback_keyboard([
        ("🇷🇺 Москва (UTC+3)", "tz_Europe/Moscow"),
        ("🇷🇺 Самара (UTC+4)", "tz_Europe/Samara"),
        ("🇷🇺 Екатеринбург (UTC+5)", "tz_Asia/Yekaterinburg"),
        ("🇷🇺 Новосибирск (UTC+7)", "tz_Asia/Novosibirsk"),
        ("🇷🇺 Владивосток (UTC+10)", "tz_Asia/Vladivostok"),
    ])
    await _send(api, peer_id,
                "🌍 Часовой пояс\n\nВыберите ваш часовой пояс:",
                keyboard=keyboard)


async def vk_handle_time_callback(api, peer_id, user_id, cmid, action):
    """Обработчик выбора времени напоминаний"""
    if not action.startswith("time_"):
        return

    time_str = action.replace("time_", "")

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(vk_id=user_id).first()
        if not user:
            await _send(api, peer_id, "Вы ещё не начали практики. Напишите 'Начать'")
            return

        user.preferred_time = time_str
        user.last_reminder_sent = datetime.utcnow()
        db.commit()

        await _edit(api, peer_id, cmid,
                    f"✅ Время напоминаний установлено!\n\n"
                    f"Вы будете получать напоминания каждый день в {time_str}.\n\n"
                    f"Часовой пояс: {user.timezone}")

        logger.info(f"[VK] Пользователь {user_id} установил время: {time_str}")
    finally:
        db.close()


async def vk_handle_timezone_callback(api, peer_id, user_id, cmid, action):
    """Обработчик выбора часового пояса"""
    if not action.startswith("tz_"):
        return

    timezone_str = action.replace("tz_", "")

    db = SessionLocal()
    try:
        user = db.query(User).filter_by(vk_id=user_id).first()
        if not user:
            await _send(api, peer_id, "Вы ещё не начали практики. Напишите 'Начать'")
            return

        user.timezone = timezone_str
        db.commit()

        import pytz
        tz = pytz.timezone(timezone_str)
        current_time = datetime.now(tz).strftime("%H:%M")

        await _edit(api, peer_id, cmid,
                    f"✅ Часовой пояс установлен!\n\n"
                    f"Ваш часовой пояс: {timezone_str}\n"
                    f"Текущее время: {current_time}")

        logger.info(f"[VK] Пользователь {user_id} установил часовой пояс: {timezone_str}")
    finally:
        db.close()
