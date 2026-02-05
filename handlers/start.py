"""
Обработчики команд /start и /menu
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import ContextTypes
from utils import error_handler, get_or_create_user
from models import SessionLocal, User

logger = logging.getLogger(__name__)

# Постоянная клавиатура с кнопкой "Меню"
MENU_KEYBOARD = ReplyKeyboardMarkup(
    [["📋 Меню"]],
    resize_keyboard=True,
    is_persistent=True
)


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
        "Готов(а) начать? 🌿"
    )

    # Определяем, куда вести пользователя
    if user_stage > 1 or user_step > 1:
        # Пользователь уже проходил практики
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Давай начнем 🌱", callback_data="start_show_status")]
        ])
    else:
        # Новый пользователь - начать практики
        inline_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Давай начнем 🌱", callback_data="start_practice_from_start")]
        ])

    # Отправляем сообщение с Inline-кнопкой
    await update.message.reply_text(welcome_message, reply_markup=inline_keyboard)

    # Показываем постоянную кнопку "Меню"
    await update.message.reply_text(
        "Используй кнопку 📋 Меню внизу для доступа к настройкам.",
        reply_markup=MENU_KEYBOARD
    )


def get_menu_keyboard():
    """Создать клавиатуру главного меню"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Продолжить практику", callback_data="menu_continue")],
        [InlineKeyboardButton("🔄 Начать заново", callback_data="menu_reset")],
        [InlineKeyboardButton("📊 Мой прогресс", callback_data="menu_status")],
        [InlineKeyboardButton("⏰ Время напоминаний", callback_data="menu_set_time")],
        [InlineKeyboardButton("🌍 Часовой пояс", callback_data="menu_timezone")],
        [InlineKeyboardButton("📞 Поддержка", callback_data="menu_contact")],
    ])


@error_handler
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /menu — показать главное меню"""
    await update.message.reply_text(
        "📋 **Главное меню**\n\nВыбери нужное действие:",
        reply_markup=get_menu_keyboard(),
        parse_mode='Markdown'
    )


@error_handler
async def handle_menu_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатия кнопки '📋 Меню' (ReplyKeyboard)"""
    await update.message.reply_text(
        "📋 **Главное меню**\n\nВыбери нужное действие:",
        reply_markup=get_menu_keyboard(),
        parse_mode='Markdown'
    )


@error_handler
async def handle_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий кнопок главного меню"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    action = query.data

    if action == "menu_continue":
        # Продолжить практику
        from handlers.practices import handle_continue_practice_logic
        await handle_continue_practice_logic(query, user_id)

    elif action == "menu_reset":
        # Показать подтверждение сброса
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, начать заново", callback_data="confirm_reset"),
                InlineKeyboardButton("❌ Отмена", callback_data="cancel_reset")
            ]
        ])
        await query.message.reply_text(
            "🔄 **Сброс прогресса**\n\n"
            "Вы уверены, что хотите начать практики заново?\n"
            "Весь текущий прогресс будет сброшен.",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    elif action == "menu_status":
        # Показать прогресс
        db = SessionLocal()
        try:
            db_user = db.query(User).filter_by(telegram_id=user_id).first()
            if db_user:
                status_text = (
                    f"📊 **Твой прогресс**\n\n"
                    f"🌱 Этап: {db_user.current_stage} из 6\n"
                    f"📅 День: {db_user.current_day}\n"
                    f"👣 Шаг: {db_user.current_step}\n"
                    f"⏸ Статус: {'На паузе' if db_user.is_paused else 'Активно'}"
                )
                await query.message.reply_text(status_text, parse_mode='Markdown')
            else:
                await query.message.reply_text("Вы ещё не начали практики. Нажмите /start")
        finally:
            db.close()

    elif action == "menu_set_time":
        # Показать выбор времени
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("09:00", callback_data="time_09:00"),
                InlineKeyboardButton("10:00", callback_data="time_10:00"),
                InlineKeyboardButton("11:00", callback_data="time_11:00"),
            ],
            [
                InlineKeyboardButton("12:00", callback_data="time_12:00"),
                InlineKeyboardButton("13:00", callback_data="time_13:00"),
                InlineKeyboardButton("14:00", callback_data="time_14:00"),
            ],
            [
                InlineKeyboardButton("18:00", callback_data="time_18:00"),
                InlineKeyboardButton("19:00", callback_data="time_19:00"),
                InlineKeyboardButton("20:00", callback_data="time_20:00"),
            ],
        ])
        await query.message.reply_text(
            "⏰ **Время напоминаний**\n\nВыберите удобное время:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    elif action == "menu_timezone":
        # Показать выбор часового пояса (города РФ)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇷🇺 Москва (UTC+3)", callback_data="tz_Europe/Moscow")],
            [InlineKeyboardButton("🇷🇺 Самара (UTC+4)", callback_data="tz_Europe/Samara")],
            [InlineKeyboardButton("🇷🇺 Екатеринбург (UTC+5)", callback_data="tz_Asia/Yekaterinburg")],
            [InlineKeyboardButton("🇷🇺 Новосибирск (UTC+7)", callback_data="tz_Asia/Novosibirsk")],
            [InlineKeyboardButton("🇷🇺 Владивосток (UTC+10)", callback_data="tz_Asia/Vladivostok")],
        ])
        await query.message.reply_text(
            "🌍 **Часовой пояс**\n\nВыберите ваш часовой пояс:",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

    elif action == "menu_contact":
        # Показать контакт поддержки
        await query.message.reply_text(
            "📞 **Поддержка**\n\n"
            "По всем вопросам пишите:\n"
            "💬 Telegram: @sogreto_support\n\n"
            "Мы ответим в течение 24 часов."
        )


@error_handler
async def handle_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback'ов от кнопки 'Да, тык' в /start"""
    query = update.callback_query
    await query.answer()

    if query.data == "start_show_status":
        # Показать статус пользователя
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
