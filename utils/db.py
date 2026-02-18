"""
Утилиты для работы с базой данных
"""
from sqlalchemy.orm import Session
from models import User, UserProgress, ScheduledReminder
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def get_or_create_user(db: Session, telegram_id: int, username: str = None,
                       first_name: str = None, last_name: str = None) -> User:
    """
    Получить существующего пользователя или создать нового

    Args:
        db: Сессия БД
        telegram_id: ID пользователя в Telegram
        username: Username пользователя
        first_name: Имя
        last_name: Фамилия

    Returns:
        User: Объект пользователя
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Создан новый пользователь: {telegram_id}")
    else:
        # Обновить информацию о пользователе
        user.username = username
        user.first_name = first_name
        user.last_name = last_name
        user.last_interaction = datetime.utcnow()
        db.commit()

    return user


def get_or_create_vk_user(db: Session, vk_id: int,
                          first_name: str = None, last_name: str = None) -> User:
    """
    Получить существующего VK-пользователя или создать нового

    Args:
        db: Сессия БД
        vk_id: ID пользователя ВКонтакте
        first_name: Имя
        last_name: Фамилия

    Returns:
        User: Объект пользователя
    """
    user = db.query(User).filter(User.vk_id == vk_id).first()

    if not user:
        user = User(
            platform='vk',
            vk_id=vk_id,
            first_name=first_name,
            last_name=last_name
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"Создан новый VK-пользователь: {vk_id}")
    else:
        user.first_name = first_name
        user.last_name = last_name
        user.last_interaction = datetime.utcnow()
        db.commit()

    return user


def update_user_progress(db: Session, telegram_id: int, stage_id: int,
                        step_id: int, day: int, user_response: str = None):
    """
    Обновить прогресс пользователя

    Args:
        db: Сессия БД
        telegram_id: ID пользователя
        stage_id: ID этапа
        step_id: ID шага
        day: День практики
        user_response: Ответ пользователя (если есть)
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()

    if user:
        user.current_stage = stage_id
        user.current_step = step_id
        user.current_day = day
        user.last_interaction = datetime.utcnow()

        # Записать в историю
        progress = UserProgress(
            user_telegram_id=telegram_id,
            stage_id=stage_id,
            step_id=step_id,
            day=day,
            user_response=user_response
        )
        db.add(progress)
        db.commit()
        logger.info(f"Обновлён прогресс пользователя {telegram_id}: stage={stage_id}, step={step_id}, day={day}")


def pause_user(db: Session, telegram_id: int):
    """Поставить практики на паузу"""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user:
        user.is_paused = True
        user.paused_at = datetime.utcnow()
        db.commit()
        logger.info(f"Пользователь {telegram_id} поставил практики на паузу")


def resume_user(db: Session, telegram_id: int):
    """Возобновить практики"""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user:
        user.is_paused = False
        user.resumed_at = datetime.utcnow()
        db.commit()
        logger.info(f"Пользователь {telegram_id} возобновил практики")


def reset_user_progress(db: Session, telegram_id: int):
    """Сбросить прогресс пользователя (начать сначала)"""
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if user:
        user.current_stage = 1
        user.current_step = 1
        user.current_day = 1
        user.is_paused = False
        user.paused_at = None
        db.commit()
        logger.info(f"Прогресс пользователя {telegram_id} сброшен")


def get_user_stats(db: Session, telegram_id: int) -> dict:
    """
    Получить статистику пользователя

    Returns:
        dict: Словарь со статистикой
    """
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        return None

    completed_steps = db.query(UserProgress).filter(
        UserProgress.user_telegram_id == telegram_id
    ).count()

    return {
        'telegram_id': user.telegram_id,
        'username': user.username,
        'current_stage': user.current_stage,
        'current_step': user.current_step,
        'current_day': user.current_day,
        'is_paused': user.is_paused,
        'completed_steps': completed_steps,
        'created_at': user.created_at,
        'last_interaction': user.last_interaction
    }


def update_user_progress_obj(db: Session, user, stage_id: int,
                             step_id: int, day: int, user_response: str = None):
    """
    Обновить прогресс пользователя (platform-agnostic, принимает объект User)
    """
    user.current_stage = stage_id
    user.current_step = step_id
    user.current_day = day
    user.last_interaction = datetime.utcnow()

    progress = UserProgress(
        user_telegram_id=user.platform_id,
        stage_id=stage_id,
        step_id=step_id,
        day=day,
        user_response=user_response
    )
    db.add(progress)
    db.commit()
    logger.info(f"Обновлён прогресс {user.platform}:{user.platform_id}: stage={stage_id}, step={step_id}, day={day}")


def reset_user_progress_obj(db: Session, user):
    """Сбросить прогресс пользователя (platform-agnostic)"""
    user.current_stage = 1
    user.current_step = 1
    user.current_day = 1
    user.is_paused = False
    user.paused_at = None
    user.daily_practice_day = 0
    user.daily_practice_substep = ""
    user.last_practice_date = None
    user.reminder_postponed = False
    user.postponed_until = None
    user.awaiting_sprouts = False
    db.commit()
    logger.info(f"Прогресс {user.platform}:{user.platform_id} сброшен")


def delete_user_data(db: Session, telegram_id: int):
    """
    Удалить все данные пользователя (GDPR)

    Args:
        db: Сессия БД
        telegram_id: ID пользователя
    """
    # Удалить историю прогресса
    db.query(UserProgress).filter(UserProgress.user_telegram_id == telegram_id).delete()

    # Удалить напоминания
    db.query(ScheduledReminder).filter(ScheduledReminder.user_telegram_id == telegram_id).delete()

    # Удалить пользователя
    db.query(User).filter(User.telegram_id == telegram_id).delete()

    db.commit()
    logger.info(f"Данные пользователя {telegram_id} удалены (GDPR)")
