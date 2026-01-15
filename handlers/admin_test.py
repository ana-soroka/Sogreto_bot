"""
Обработчики callback для админского тестового меню
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from models import SessionLocal, User
from handlers.admin import ADMIN_IDS
from utils.scheduler import send_daily_practice_reminder, send_stage4_reminder

logger = logging.getLogger(__name__)


async def handle_admin_test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для админского тестового меню"""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    action = query.data

    # Проверка прав администратора
    if user.id not in ADMIN_IDS:
        await query.edit_message_text("⛔ У вас нет прав для выполнения этой команды.")
        return

    db = SessionLocal()

    try:
        db_user = db.query(User).filter(User.telegram_id == user.id).first()

        if not db_user:
            await query.edit_message_text("❌ Пользователь не найден в БД")
            return

        if action == "admin_refresh_status":
            # Обновить статус
            status_text = (
                f"🛠 **Админское тестовое меню**\n\n"
                f"**Текущее состояние:**\n"
                f"• Этап: {db_user.current_stage}\n"
                f"• Шаг: {db_user.current_step}\n"
                f"• День: {db_user.current_day}\n"
                f"• Daily practice day: {db_user.daily_practice_day}\n"
                f"• Daily substep: {db_user.daily_practice_substep or '(нет)'}\n"
                f"• Stage 4 reminder: {db_user.stage4_reminder_date or '(не установлено)'}\n\n"
                f"**Выберите тест:**"
            )

            keyboard = [
                [InlineKeyboardButton("🧪 Тест: День 1 (Stage 3)", callback_data="admin_test_day1")],
                [InlineKeyboardButton("🧪 Тест: День 2 (Stage 3)", callback_data="admin_test_day2")],
                [InlineKeyboardButton("🧪 Тест: День 3 (Stage 3)", callback_data="admin_test_day3")],
                [InlineKeyboardButton("🧪 Тест: День 4 (Stage 3)", callback_data="admin_test_day4")],
                [InlineKeyboardButton("🧪 Тест: Якорь (Stage 4)", callback_data="admin_test_stage4")],
                [InlineKeyboardButton("📊 Обновить статус", callback_data="admin_refresh_status")],
            ]

            await query.edit_message_text(
                status_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
            logger.info(f"Администратор {user.id} обновил статус")

        elif action == "admin_test_day1":
            # Тест напоминания День 1
            db_user.daily_practice_day = 1
            db.commit()
            await send_daily_practice_reminder(context.bot, db_user, db)
            await query.answer("✅ Отправлено напоминание День 1!", show_alert=True)
            logger.info(f"Администратор {user.id} отправил тест День 1")

        elif action == "admin_test_day2":
            # Тест напоминания День 2
            db_user.daily_practice_day = 2
            db.commit()
            await send_daily_practice_reminder(context.bot, db_user, db)
            await query.answer("✅ Отправлено напоминание День 2!", show_alert=True)
            logger.info(f"Администратор {user.id} отправил тест День 2")

        elif action == "admin_test_day3":
            # Тест напоминания День 3
            db_user.daily_practice_day = 3
            db.commit()
            await send_daily_practice_reminder(context.bot, db_user, db)
            await query.answer("✅ Отправлено напоминание День 3!", show_alert=True)
            logger.info(f"Администратор {user.id} отправил тест День 3")

        elif action == "admin_test_day4":
            # Тест напоминания День 4
            db_user.daily_practice_day = 4
            db.commit()
            await send_daily_practice_reminder(context.bot, db_user, db)
            await query.answer("✅ Отправлено напоминание День 4!", show_alert=True)
            logger.info(f"Администратор {user.id} отправил тест День 4")

        elif action == "admin_test_stage4":
            # Тест напоминания Stage 4 (Якорь)
            await send_stage4_reminder(context.bot, db_user, db)
            await query.answer("✅ Отправлено напоминание Якорь (Stage 4)!", show_alert=True)
            logger.info(f"Администратор {user.id} отправил тест Stage 4")

    except Exception as e:
        await query.answer(f"❌ Ошибка: {str(e)}", show_alert=True)
        logger.error(f"Ошибка в админском тестовом меню: {e}")

    finally:
        db.close()
