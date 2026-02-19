"""
Sogreto VK Bot — Бот практик предвкушения для ВКонтакте
Точка входа (long-poll)
"""
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv

from vkbottle.bot import Bot, Message
from vkbottle import GroupEventType, GroupTypes

from models import init_db
from utils import practices_manager
from utils.vk_keyboards import create_vk_menu_keyboard

load_dotenv()


def setup_logging():
    """Настроить логирование для VK-бота"""
    os.makedirs('logs', exist_ok=True)
    log_format = '%(asctime)s - [VK] %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    logging.basicConfig(level=logging.INFO, format=log_format, datefmt=date_format)

    file_handler = RotatingFileHandler(
        'logs/vk_bot.log', maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(log_format, date_format))
    logging.getLogger('').addHandler(file_handler)
    logging.getLogger('vkbottle').setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("=" * 50)
    logger.info("Sogreto VK Bot запускается...")
    logger.info("=" * 50)


setup_logging()
logger = logging.getLogger(__name__)

VK_TOKEN = os.getenv('VK_BOT_TOKEN')
if not VK_TOKEN:
    logger.error("VK_BOT_TOKEN не найден в .env!")
    raise SystemExit("VK_BOT_TOKEN не найден")

bot = Bot(token=VK_TOKEN)


# ==================== ТЕКСТОВЫЕ КОМАНДЫ ====================

@bot.on.message(text=["Начать", "начать", "Start", "start"])
async def handle_start(message: Message):
    """Приветствие"""
    try:
        from vk_handlers.start import vk_start_command
        await vk_start_command(bot.api, message)
    except Exception as e:
        logger.error(f"[VK] Ошибка в handle_start: {e}", exc_info=True)


@bot.on.message(text=["Меню", "меню", "📋 Меню", "Menu", "menu"])
async def handle_menu(message: Message):
    """Главное меню"""
    try:
        from vk_handlers.start import vk_menu_command
        await vk_menu_command(bot.api, message)
    except Exception as e:
        logger.error(f"[VK] Ошибка в handle_menu: {e}", exc_info=True)


@bot.on.message(text=["Статус", "статус", "Status"])
async def handle_status(message: Message):
    """Показать прогресс"""
    try:
        from vk_handlers.user import vk_status_command
        await vk_status_command(bot.api, message)
    except Exception as e:
        logger.error(f"[VK] Ошибка в handle_status: {e}", exc_info=True)


@bot.on.message(text=["Пауза", "пауза", "Pause"])
async def handle_pause(message: Message):
    """Пауза практик"""
    try:
        from vk_handlers.user import vk_pause_command
        await vk_pause_command(bot.api, message)
    except Exception as e:
        logger.error(f"[VK] Ошибка в handle_pause: {e}", exc_info=True)


@bot.on.message(text=["Продолжить", "продолжить", "Resume"])
async def handle_resume(message: Message):
    """Возобновить практики"""
    try:
        from vk_handlers.user import vk_resume_command
        await vk_resume_command(bot.api, message)
    except Exception as e:
        logger.error(f"[VK] Ошибка в handle_resume: {e}", exc_info=True)


@bot.on.message()
async def handle_other(message: Message):
    """Все остальные сообщения — также обрабатываем текстовые команды как fallback"""
    try:
        text = (message.text or "").strip().lower()
        logger.info(f"[VK] handle_other: from_id={message.from_id}, text={repr(message.text)}")

        if text in ("меню", "menu", "📋 меню"):
            from vk_handlers.start import vk_menu_command
            await vk_menu_command(bot.api, message)
        elif text in ("начать", "start"):
            from vk_handlers.start import vk_start_command
            await vk_start_command(bot.api, message)
        elif text in ("статус", "status"):
            from vk_handlers.user import vk_status_command
            await vk_status_command(bot.api, message)
        elif text in ("пауза", "pause"):
            from vk_handlers.user import vk_pause_command
            await vk_pause_command(bot.api, message)
        elif text in ("продолжить", "resume"):
            from vk_handlers.user import vk_resume_command
            await vk_resume_command(bot.api, message)
        else:
            await message.answer(
                "Я не понимаю эту команду.\n"
                "Напиши \"Меню\" для доступа к функциям.",
                keyboard=create_vk_menu_keyboard()
            )
    except Exception as e:
        logger.error(f"[VK] Ошибка в handle_other: {e}", exc_info=True)


# ==================== CALLBACK-КНОПКИ ====================

@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=GroupTypes.MessageEvent)
async def handle_callback(event: GroupTypes.MessageEvent):
    """Обработчик нажатий callback-кнопок (аналог Telegram CallbackQueryHandler)"""
    try:
        peer_id = event.object.peer_id
        user_id = event.object.user_id
        event_id = event.object.event_id
        cmid = event.object.conversation_message_id
        payload = event.object.payload

        # Парсим payload
        if isinstance(payload, str):
            payload = json.loads(payload)

        action = payload.get('action', '') if payload else ''

        logger.info(f"[VK] Callback от {user_id}: action={action}")

        # Подтвердить нажатие кнопки
        await bot.api.messages.send_message_event_answer(
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id
        )

        # --- Start callbacks ---
        if action in ("start_show_status", "start_practice_from_start"):
            from vk_handlers.start import vk_handle_start_callback
            await vk_handle_start_callback(bot.api, peer_id, user_id, cmid, action)

        # --- Menu callbacks ---
        elif action.startswith("menu_"):
            from vk_handlers.start import vk_handle_menu_callback
            await vk_handle_menu_callback(bot.api, peer_id, user_id, cmid, action)

        # --- Time setting callbacks ---
        elif action.startswith("time_"):
            from vk_handlers.settings import vk_handle_time_callback
            await vk_handle_time_callback(bot.api, peer_id, user_id, cmid, action)

        # --- Timezone setting callbacks ---
        elif action.startswith("tz_"):
            from vk_handlers.settings import vk_handle_timezone_callback
            await vk_handle_timezone_callback(bot.api, peer_id, user_id, cmid, action)

        # --- Practice callbacks (всё остальное) ---
        else:
            from vk_handlers.practices import vk_handle_practice_callback
            await vk_handle_practice_callback(bot.api, peer_id, user_id, cmid, action)

    except Exception as e:
        logger.error(f"[VK] Ошибка обработки callback: {e}", exc_info=True)


# ==================== ЗАПУСК ====================

def main():
    """Запуск VK-бота"""
    logger.info("Инициализация базы данных...")
    init_db()

    logger.info("Загрузка практик...")
    try:
        practices_manager.load_practices()
        logger.info(f"Загружено этапов: {practices_manager.get_total_stages()}")
    except Exception as e:
        logger.error(f"Ошибка загрузки практик: {e}")
        return

    logger.info("VK-бот запущен! Нажмите Ctrl+C для остановки.")
    bot.run_forever()


if __name__ == '__main__':
    main()
