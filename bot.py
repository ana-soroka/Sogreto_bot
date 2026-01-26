"""
Sogreto Bot - Бот практик предвкушения
Главный файл бота
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

from models import init_db
from utils import error_handler, global_error_handler, practices_manager
from utils.scheduler import init_scheduler, schedule_user_reminders, stop_scheduler

# Импортируем обработчики из handlers/
from handlers import (
    start_command,
    help_command,
    handle_start_callback,
    status_command,
    pause_command,
    resume_command,
    reset_command,
    examples_command,
    recipes_command,
    manifesto_command,
    contact_command,
    start_practice_command,
    handle_practice_callback,
    set_time_command,
    timezone_command,
    handle_time_callback,
    handle_timezone_callback,
    reload_practices_command,
    handle_web_app_data,
)
from handlers.admin import admin_test_command
from handlers.admin_test import handle_admin_test_callback
from handlers.admin_fast_test import (
    test_wait_scheduler_command,
    test_status_command,
    test_reset_command,
    admin_check_user_command,
    admin_users_command
)

# Загрузка переменных окружения
load_dotenv()


# Настройка логирования
def setup_logging():
    """Настроить систему логирования"""
    os.makedirs('logs', exist_ok=True)

    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format
    )

    file_handler = RotatingFileHandler(
        'logs/bot.log',
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))

    logging.getLogger('').addHandler(file_handler)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("="*50)
    logger.info("Sogreto Bot запускается...")
    logger.info("="*50)


setup_logging()
logger = logging.getLogger(__name__)


# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ОБРАБОТЧИКИ
# ============================================================================

@error_handler
async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик неизвестных команд"""
    await update.message.reply_text(
        "Извините, я не понимаю эту команду.\n"
        "Используйте /help чтобы увидеть список доступных команд."
    )


@error_handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений (не команд)"""
    await update.message.reply_text(
        "Используйте команды для взаимодействия со мной.\n"
        "Введите /help чтобы увидеть список команд."
    )


# ============================================================================
# ГЛАВНАЯ ФУНКЦИЯ
# ============================================================================

def main():
    """Запуск бота"""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN не найден в .env файле!")
        return

    # Инициализировать базу данных
    logger.info("Инициализация базы данных...")
    init_db()

    # Загрузить практики
    logger.info("Загрузка практик...")
    try:
        practices_manager.load_practices()
        logger.info(f"Загружено этапов: {practices_manager.get_total_stages()}")
    except Exception as e:
        logger.error(f"Ошибка загрузки практик: {e}")
        return

    # Создать приложение
    logger.info("Создание приложения...")
    application = Application.builder().token(token).build()

    # Зарегистрировать обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("reset", reset_command))
    application.add_handler(CommandHandler("examples", examples_command))
    application.add_handler(CommandHandler("recipes", recipes_command))
    application.add_handler(CommandHandler("manifesto", manifesto_command))
    application.add_handler(CommandHandler("contact", contact_command))
    application.add_handler(CommandHandler("start_practice", start_practice_command))
    application.add_handler(CommandHandler("set_time", set_time_command))
    application.add_handler(CommandHandler("timezone", timezone_command))

    # Админские команды
    application.add_handler(CommandHandler("reload_practices", reload_practices_command))
    application.add_handler(CommandHandler("admin_test", admin_test_command))

    # Тестовые команды для проверки автоматической работы scheduler (только для админов)
    application.add_handler(CommandHandler("test_wait_scheduler", test_wait_scheduler_command))
    application.add_handler(CommandHandler("test_status", test_status_command))
    application.add_handler(CommandHandler("test_reset", test_reset_command))
    application.add_handler(CommandHandler("admin_check_user", admin_check_user_command))
    application.add_handler(CommandHandler("admin_users", admin_users_command))

    # Обработчик нажатий на кнопки (callback_query)
    # Используем паттерны для разных типов кнопок
    application.add_handler(CallbackQueryHandler(handle_practice_callback, pattern="^(next_step|prev_step|complete_stage|show_examples_menu|toggle_category_.*|continue_from_examples|show_recipes|expand_recipe_.*|collapse_recipe_.*|show_manifesto|start_daily_practices|sprouts_appeared|continue_practice|confirm_reset|cancel_reset|test_daily_reminder|start_daily_substep|next_daily_substep|prev_daily_substep|daily_choice_A|daily_choice_B|complete_day4_practice|test_stage4_reminder|postpone_reminder|start_waiting_for_daily|stage5_start_substep|stage5_next_substep|stage5_prev_substep|start_stage6_finale|stage1_tz_.*|stage1_time_.*|replant_start|replant_step_\\d+|replant_complete|mold_start|mold_complete|mold_sprouts_start|mold_sprouts_complete)$"))
    application.add_handler(CallbackQueryHandler(handle_admin_test_callback, pattern="^(admin_test_day[1-4]|admin_test_stage4|admin_test_stage5_menu|admin_test_stage5_day[1-7]|admin_test_stage6|admin_test_stage2_menu|admin_test_stage2_day[2-5]|admin_refresh_status)$"))
    application.add_handler(CallbackQueryHandler(handle_time_callback, pattern="^time_"))
    application.add_handler(CallbackQueryHandler(handle_timezone_callback, pattern="^tz_"))
    application.add_handler(CallbackQueryHandler(handle_start_callback, pattern="^start_"))

    # Обработчик Web App данных (должен быть перед текстовыми обработчиками)
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    # Обработчик неизвестных команд
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Обработчик текстовых сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Глобальный обработчик ошибок
    application.add_error_handler(global_error_handler)

    # Инициализировать планировщик напоминаний
    logger.info("Инициализация планировщика напоминаний...")
    init_scheduler()
    schedule_user_reminders(application.bot)
    logger.info("Планировщик настроен (проверка каждый час)")

    # Запустить бота
    logger.info("Бот запущен! Нажмите Ctrl+C для остановки.")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except KeyboardInterrupt:
        logger.info("Остановка бота...")
        stop_scheduler()
        logger.info("Бот остановлен")


if __name__ == '__main__':
    main()
