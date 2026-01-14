"""
Модуль обработки ошибок для Sogreto Bot

Этот модуль предоставляет декораторы и функции для централизованной
обработки ошибок, логирования и уведомлений об ошибках.
"""

import logging
import functools
import traceback
from telegram import Update
from telegram.error import (
    TelegramError,
    NetworkError,
    BadRequest,
    TimedOut,
    Forbidden
)
from telegram.ext import ContextTypes

# Настройка логгера
logger = logging.getLogger(__name__)


class BotError(Exception):
    """Базовый класс для ошибок бота"""
    pass


class PracticeNotFoundError(BotError):
    """Ошибка: практика не найдена"""
    pass


class UserNotFoundError(BotError):
    """Ошибка: пользователь не найден в БД"""
    pass


class DatabaseError(BotError):
    """Ошибка работы с базой данных"""
    pass


def error_handler(func):
    """
    Декоратор для обработки ошибок в handlers

    Использование:
        @error_handler
        async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            # ваш код
    """
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            return await func(update, context)

        except Forbidden:
            # Пользователь заблокировал бота
            logger.warning(f"User {update.effective_user.id} blocked the bot")
            # Помечаем пользователя как неактивного в БД
            # TODO: db.mark_user_inactive(update.effective_user.id)

        except BadRequest as e:
            # Неверный запрос к Telegram API
            logger.error(f"Bad request in {func.__name__}: {e}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла ошибка. Попробуйте ещё раз."
                )

        except TimedOut:
            # Timeout при отправке сообщения
            logger.error(f"Timeout in {func.__name__}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Соединение прервано. Повторите запрос через несколько секунд."
                )

        except NetworkError as e:
            # Проблемы с сетью
            logger.error(f"Network error in {func.__name__}: {e}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Проблемы с соединением. Попробуйте позже."
                )

        except TelegramError as e:
            # Любая другая ошибка Telegram API
            logger.error(f"Telegram error in {func.__name__}: {e}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла ошибка при связи с Telegram. Попробуйте позже."
                )

        except PracticeNotFoundError as e:
            # Практика не найдена в JSON
            logger.error(f"Practice not found: {e}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Практика не найдена. Обратитесь в поддержку."
                )

        except UserNotFoundError as e:
            # Пользователь не найден в БД
            logger.error(f"User not found: {e}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Ваши данные не найдены. Попробуйте начать заново с /start"
                )

        except DatabaseError as e:
            # Ошибка БД
            logger.critical(f"Database error in {func.__name__}: {e}")
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Ошибка базы данных. Администраторы уже уведомлены."
                )
            # TODO: Отправить алерт админу
            # await send_admin_alert(f"DB Error: {e}")

        except Exception as e:
            # Неожиданная ошибка
            logger.critical(
                f"Unexpected error in {func.__name__}: {e}\n"
                f"Traceback: {traceback.format_exc()}"
            )
            if update.effective_message:
                await update.effective_message.reply_text(
                    "Произошла непредвиденная ошибка. Администраторы уже уведомлены."
                )
            # TODO: Отправить алерт админу
            # await send_admin_alert(f"Critical Error in {func.__name__}: {e}")

    return wrapper


def safe_execute(func, *args, **kwargs):
    """
    Безопасное выполнение функции с логированием ошибок

    Использование:
        result = safe_execute(some_function, arg1, arg2, kwarg1=value1)
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Error in {func.__name__}: {e}")
        return None


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Глобальный обработчик ошибок для всего бота

    Регистрация:
        application.add_error_handler(global_error_handler)
    """
    logger.error(f"Exception while handling an update: {context.error}")

    # Логируем traceback
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = ''.join(tb_list)
    logger.error(f"Traceback:\n{tb_string}")

    # TODO: Отправить админу детальную информацию
    # await send_admin_alert(f"Global error: {context.error}\n{tb_string[:500]}")

    # Если это Update с сообщением, отправляем пользователю
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "Произошла ошибка. Наша команда уже работает над её устранением."
        )


def validate_user_input(text: str, max_length: int = 1000) -> bool:
    """
    Валидация пользовательского ввода

    Args:
        text: Текст от пользователя
        max_length: Максимальная длина

    Returns:
        True если валидно, False если нет
    """
    if not text:
        return False

    if len(text) > max_length:
        logger.warning(f"Input too long: {len(text)} > {max_length}")
        return False

    # Проверка на потенциально опасные символы
    dangerous_chars = ['<script>', 'javascript:', 'onerror=']
    if any(char in text.lower() for char in dangerous_chars):
        logger.warning(f"Dangerous input detected: {text[:100]}")
        return False

    return True


async def send_admin_alert(message: str, admin_id: int = None):
    """
    Отправить алерт администратору

    Args:
        message: Текст алерта
        admin_id: ID администратора в Telegram (из конфига)

    TODO: Реализовать после настройки бота
    """
    # from bot import application
    # if admin_id:
    #     await application.bot.send_message(
    #         chat_id=admin_id,
    #         text=f"🚨 ALERT:\n{message}"
    #     )
    pass


# Пример использования:
"""
from utils.error_handling import error_handler

@error_handler
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(f"Привет, {user.first_name}!")
"""
