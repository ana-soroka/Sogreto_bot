"""
VK обработчики: статус, пауза, возобновление
"""
import logging
from datetime import datetime
from models import SessionLocal, User
from utils.db import get_or_create_vk_user
from utils.vk_keyboards import create_vk_callback_keyboard

logger = logging.getLogger(__name__)


async def _get_vk_user_info(api, user_id: int):
    """Получить имя VK-пользователя"""
    try:
        users = await api.users.get(user_ids=[user_id])
        if users:
            return users[0].first_name, users[0].last_name
    except:
        pass
    return None, None


async def vk_status_command(api, message):
    """Показать прогресс пользователя"""
    user_id = message.from_id

    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(vk_id=user_id).first()
        if not db_user:
            await message.answer("У вас ещё нет прогресса. Напишите 'Начать' для начала практик.")
            return

        status_message = (
            f"Ваш прогресс 🌱\n\n"
            f"📍 Этап: {db_user.current_stage} из 6\n"
            f"📝 Шаг: {db_user.current_step}\n"
            f"📅 День: {db_user.current_day}\n"
            f"⏸ Статус: {'На паузе' if db_user.is_paused else 'Активно'}\n\n"
            f"Дата начала: {db_user.created_at.strftime('%d.%m.%Y')}\n"
            f"Последняя активность: {db_user.last_interaction.strftime('%d.%m.%Y %H:%M')}\n\n"
            "Продолжай в том же духе! 💪"
        )

        keyboard = create_vk_callback_keyboard([
            ("▶️ Продолжить практику", "continue_practice")
        ])

        await message.answer(status_message, keyboard=keyboard)
    finally:
        db.close()


async def vk_pause_command(api, message):
    """Поставить практики на паузу"""
    user_id = message.from_id

    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(vk_id=user_id).first()
        if db_user:
            db_user.is_paused = True
            db_user.paused_at = datetime.utcnow()
            db.commit()

            await message.answer(
                "⏸ Практики приостановлены.\n\n"
                "Напоминания не будут приходить, пока ты не возобновишь практики "
                "(напиши 'Продолжить').\n\n"
                "Возвращайся скорее! 🌱"
            )
            logger.info(f"[VK] Пользователь {user_id} приостановил практики")
        else:
            await message.answer("Вы ещё не начали практики. Напишите 'Начать'")
    finally:
        db.close()


async def vk_resume_command(api, message):
    """Возобновить практики"""
    user_id = message.from_id

    db = SessionLocal()
    try:
        db_user = db.query(User).filter_by(vk_id=user_id).first()
        if db_user:
            db_user.is_paused = False
            db_user.resumed_at = datetime.utcnow()
            db.commit()

            await message.answer(
                "▶️ Практики возобновлены!\n\n"
                "Напоминания снова будут приходить по расписанию.\n\n"
                "Рад что ты вернулся(лась)! 💚"
            )
            logger.info(f"[VK] Пользователь {user_id} возобновил практики")
        else:
            await message.answer("Вы ещё не начали практики. Напишите 'Начать'")
    finally:
        db.close()
