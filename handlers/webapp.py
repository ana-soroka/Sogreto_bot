"""
Обработчики для Telegram Web App
"""
import json
import logging
from telegram import Update
from telegram.ext import ContextTypes
from models import SessionLocal, User

logger = logging.getLogger(__name__)


async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик данных, отправленных из Web App

    Когда таймер завершается, Web App отправляет данные боту,
    и этот обработчик автоматически показывает следующий шаг
    """
    logger.info(f"=== Web App handler вызван!")
    logger.info(f"Update type: {type(update)}")
    logger.info(f"Has effective_message: {hasattr(update, 'effective_message')}")
    if hasattr(update, 'effective_message') and update.effective_message:
        logger.info(f"Message: {update.effective_message}")
        logger.info(f"Has web_app_data: {hasattr(update.effective_message, 'web_app_data')}")

    try:
        # Получить данные из Web App
        if not update.effective_message or not update.effective_message.web_app_data:
            logger.error("Нет web_app_data в update!")
            return

        data = json.loads(update.effective_message.web_app_data.data)
        user_id = update.effective_user.id

        logger.info(f"✅ Получены данные из Web App от пользователя {user_id}: {data}")

        # Проверить, что это завершение таймера
        if data.get('action') == 'timer_completed':
            db = SessionLocal()
            try:
                db_user = db.query(User).filter_by(telegram_id=user_id).first()

                if not db_user:
                    logger.error(f"Пользователь {user_id} не найден в БД")
                    return

                # Проверить, что пользователь на подшаге "timer" в Stage 5
                if db_user.daily_practice_substep == "timer" and db_user.current_stage == 5:
                    # Импортируем здесь, чтобы избежать циклических импортов
                    from handlers.practices_stage5 import _get_stage5_daily_practice, _get_stage5_step_by_type
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

                    current_day = db_user.daily_practice_day

                    # Переход к следующему подшагу (affirmation)
                    db_user.daily_practice_substep = "affirmation"
                    db.commit()

                    # Получить практику и подшаг
                    practice = _get_stage5_daily_practice(current_day)
                    step = _get_stage5_step_by_type(practice, "affirmation")

                    if practice and step:
                        # Сформировать сообщение
                        theme = practice.get('theme', '')
                        message = f"🌱 **День {current_day} из 7: {theme}**\n\n"
                        message += step.get('text', '')

                        # Кнопка
                        button_text = "Принято. До завтра" if current_day < 7 else "Перейти к празднику зрелости"
                        keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton(button_text, callback_data="stage5_next_substep")]
                        ])

                        # Отправить новое сообщение (нельзя редактировать, так как это новое сообщение от Web App)
                        await context.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            reply_markup=keyboard,
                            parse_mode='Markdown'
                        )

                        logger.info(f"Пользователь {user_id} автоматически перешёл к подшагу 'affirmation' после таймера")
                    else:
                        logger.error(f"Не удалось получить практику или подшаг для пользователя {user_id}")
                else:
                    logger.warning(f"Пользователь {user_id} не на подшаге 'timer' (текущий: {db_user.daily_practice_substep})")

            finally:
                db.close()

    except Exception as e:
        logger.error(f"Ошибка обработки Web App данных: {e}", exc_info=True)
