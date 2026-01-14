"""
Обработчики админских команд:
/reload_practices - перезагрузить practices.json
"""
import logging
import os
from telegram import Update
from telegram.ext import ContextTypes
from utils import error_handler, practices_manager

logger = logging.getLogger(__name__)

# ID администраторов
ADMIN_IDS = [
    1585940117,  # Ваш telegram_id
]


def is_admin(user_id: int) -> bool:
    """Проверить, является ли пользователь администратором"""
    return user_id in ADMIN_IDS


@error_handler
async def reload_practices_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /reload_practices - перезагрузить practices.json"""
    user = update.effective_user

    # Проверка прав администратора
    if not is_admin(user.id):
        await update.message.reply_text(
            "⛔ У вас нет прав для выполнения этой команды."
        )
        logger.warning(f"Пользователь {user.id} ({user.username}) попытался выполнить /reload_practices без прав администратора")
        return

    try:
        # Перезагрузить practices.json
        practices_manager.load_practices()

        total_stages = practices_manager.get_total_stages()

        await update.message.reply_text(
            f"✅ **Практики перезагружены!**\n\n"
            f"📁 Файл: practices.json\n"
            f"📊 Загружено этапов: {total_stages}\n\n"
            f"Все новые тексты теперь будут отображаться пользователям."
        )

        logger.info(f"Администратор {user.id} ({user.username}) перезагрузил practices.json - загружено {total_stages} этапов")

    except FileNotFoundError:
        await update.message.reply_text(
            "❌ **Ошибка!**\n\n"
            "Файл practices.json не найден."
        )
        logger.error(f"Администратор {user.id} попытался перезагрузить practices.json, но файл не найден")

    except Exception as e:
        await update.message.reply_text(
            f"❌ **Ошибка при загрузке!**\n\n"
            f"Проверьте синтаксис JSON файла.\n\n"
            f"Ошибка: {str(e)}"
        )
        logger.error(f"Ошибка при перезагрузке practices.json: {e}")
