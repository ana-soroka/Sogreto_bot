"""
Обработчики команд /start и /help
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils import error_handler, get_or_create_user
from models import SessionLocal

logger = logging.getLogger(__name__)


@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    logger.info(f"Пользователь {user.id} ({user.username}) запустил /start")

    # Создать или получить пользователя в БД
    db = SessionLocal()
    try:
        db_user = get_or_create_user(
            db,
            telegram_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )
        logger.info(f"Пользователь в БД: {db_user}")

        # Сохраняем значения до закрытия сессии
        user_stage = db_user.current_stage
        user_step = db_user.current_step
    finally:
        db.close()

    # Приветственное сообщение
    welcome_message = (
        f"Привет, {user.first_name}! 🌱\n\n"
        "Я — твой проводник в мир практик предвкушения.\n\n"
        "Вместе мы будем выращивать кресс-салат и культивировать эмоцию предвкушения. "
        "Каждый день — новая практика, новое открытие.\n\n"
        "**Доступные команды:**\n"
        "/help - Справка по всем командам\n"
        "/contact - Связаться с поддержкой\n\n"
        "Готов(а) начать? 🌿"
    )

    # Определяем, куда вести пользователя
    # Если пользователь уже начал практики (current_step > 1 или current_stage > 1), ведём к /status
    # Иначе - к началу практик
    if user_stage > 1 or user_step > 1:
        # Пользователь уже проходил практики
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Да, тык 🌱", callback_data="start_show_status")]
        ])
    else:
        # Новый пользователь - начать практики
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Да, тык 🌱", callback_data="start_practice_from_start")]
        ])

    await update.message.reply_text(welcome_message, reply_markup=keyboard)


@error_handler
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = (
        "**Команды Sogreto Bot** 🌱\n\n"
        "**Основные:**\n"
        "/start - Начать работу с ботом\n"
        "/start_practice - Начать практики предвкушения\n"
        "/help - Показать эту справку\n\n"
        "**Управление практиками:**\n"
        "/pause - Приостановить напоминания\n"
        "/resume - Возобновить практики\n"
        "/reset - Начать практики заново\n"
        "/status - Посмотреть свой прогресс\n\n"
        "**Настройки:**\n"
        "/set_time - Установить время напоминаний\n"
        "/timezone - Установить часовой пояс\n\n"
        "**Дополнительно:**\n"
        "/contact - Связаться с поддержкой\n\n"
        "**О практиках:**\n"
        "Практики длятся 14-20 дней и разделены на 6 этапов:\n"
        "1️⃣ Посадка (День 1)\n"
        "2️⃣ Появление ростков (День 2-3)\n"
        "3️⃣ Активный рост (День 4-7)\n"
        "4️⃣ Укрепление (День 8-14)\n"
        "5️⃣ Сбор урожая (День 14-18)\n"
        "6️⃣ Завершение (День 18-20)\n\n"
        "Вопросы? Пиши /contact 💚"
    )

    await update.message.reply_text(help_text, parse_mode='Markdown')


@error_handler
async def handle_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback'ов от кнопки 'Да, тык' в /start"""
    query = update.callback_query
    await query.answer()

    if query.data == "start_show_status":
        # Показать статус пользователя
        from handlers.status import status_command
        # Создаём фейковый update с message для status_command
        await query.message.reply_text("📊 Загружаю твой прогресс...")
        # Вызываем status напрямую
        from models import User
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(telegram_id=query.from_user.id).first()
            if db_user:
                status_text = (
                    f"📊 **Твой прогресс**\n\n"
                    f"🌱 Этап: {db_user.current_stage} из 6\n"
                    f"📅 День: {db_user.current_day}\n"
                    f"👣 Шаг: {db_user.current_step}\n\n"
                    f"Используй /start\\_practice чтобы продолжить практику"
                )
                await query.message.reply_text(status_text, parse_mode='Markdown')
        finally:
            db.close()

    elif query.data == "start_practice_from_start":
        # Начать практики с начала
        from handlers.practices import create_practice_keyboard
        from utils import practices_manager
        from utils.db import update_user_progress, get_or_create_user
        from models import User

        user_id = query.from_user.id
        db = SessionLocal()
        try:
            user = get_or_create_user(
                db,
                telegram_id=user_id,
                username=query.from_user.username,
                first_name=query.from_user.first_name,
                last_name=query.from_user.last_name
            )

            # Получить первый шаг первого этапа
            first_step = practices_manager.get_step(stage_id=1, step_id=1)

            if not first_step:
                await query.message.reply_text(
                    "😞 Извините, произошла ошибка при загрузке практик."
                )
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

            # Отправить практику
            await query.message.reply_text(
                message,
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        finally:
            db.close()
