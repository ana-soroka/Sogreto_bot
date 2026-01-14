"""
Обработчики команд управления пользователем:
/status, /pause, /resume, /reset
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes
from utils import error_handler, get_user_stats, pause_user, resume_user, reset_user_progress
from models import SessionLocal

logger = logging.getLogger(__name__)


@error_handler
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /status - показать прогресс"""
    user = update.effective_user
    db = SessionLocal()
    try:
        stats = get_user_stats(db, user.id)

        if not stats:
            await update.message.reply_text(
                "У вас ещё нет прогресса. Начните практики командой /start_practice"
            )
            return

        status_message = (
            f"**Ваш прогресс** 🌱\n\n"
            f"📍 Этап: {stats['current_stage']} из 6\n"
            f"📝 Шаг: {stats['current_step']}\n"
            f"📅 День: {stats['current_day']}\n"
            f"✅ Завершено шагов: {stats['completed_steps']}\n"
            f"⏸ Статус: {'На паузе' if stats['is_paused'] else 'Активно'}\n\n"
            f"Дата начала: {stats['created_at'].strftime('%d.%m.%Y')}\n"
            f"Последняя активность: {stats['last_interaction'].strftime('%d.%m.%Y %H:%M')}\n\n"
            "Продолжай в том же духе! 💪"
        )

        await update.message.reply_text(status_message)
    finally:
        db.close()


@error_handler
async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /pause"""
    user = update.effective_user
    db = SessionLocal()
    try:
        pause_user(db, user.id)
        await update.message.reply_text(
            "⏸ Практики приостановлены.\n\n"
            "Напоминания не будут приходить, пока вы не возобновите практики командой /resume\n\n"
            "Возвращайся скорее! 🌱"
        )
        logger.info(f"Пользователь {user.id} приостановил практики")
    finally:
        db.close()


@error_handler
async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /resume"""
    user = update.effective_user
    db = SessionLocal()
    try:
        resume_user(db, user.id)
        await update.message.reply_text(
            "▶️ Практики возобновлены!\n\n"
            "Напоминания снова будут приходить по расписанию.\n\n"
            "Рад что ты вернулся(лась)! 💚"
        )
        logger.info(f"Пользователь {user.id} возобновил практики")
    finally:
        db.close()


@error_handler
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reset"""
    user = update.effective_user
    db = SessionLocal()
    try:
        reset_user_progress(db, user.id)
        await update.message.reply_text(
            "🔄 Прогресс сброшен!\n\n"
            "Вы можете начать практики заново командой /start_practice\n\n"
            "Начнём сначала! 🌱"
        )
        logger.info(f"Пользователь {user.id} сбросил прогресс")
    finally:
        db.close()
