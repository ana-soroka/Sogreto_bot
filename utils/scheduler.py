"""
Утилиты для работы с планировщиком (APScheduler)
Автоматическая отправка практик пользователям
"""
import logging
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from models import SessionLocal, User
from utils.practices import practices_manager
import pytz

logger = logging.getLogger(__name__)

# Глобальный планировщик
scheduler = AsyncIOScheduler()


def init_scheduler():
    """Инициализировать планировщик"""
    if not scheduler.running:
        scheduler.start()
        logger.info("Планировщик запущен")


def stop_scheduler():
    """Остановить планировщик"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Планировщик остановлен")


def calculate_days_since_start(user):
    """
    Рассчитать количество дней с момента начала практик

    Args:
        user: объект User из БД

    Returns:
        int: количество дней
    """
    if not user.started_at:
        return 0

    now = datetime.utcnow()
    delta = now - user.started_at
    return delta.days


def get_current_stage_for_user(user):
    """
    Определить, на каком этапе должен быть пользователь
    на основе количества дней с начала практик

    Args:
        user: объект User из БД

    Returns:
        int: номер этапа (1-6)
    """
    days = calculate_days_since_start(user)

    # Расписание из practices.json:
    # Этап 1: день 1 (immediate)
    # Этап 2: дни 2-4
    # Этап 3: дни 5-7
    # Этап 4: день 7
    # Этап 5: дни 8-14 (7 дней)
    # Этап 6: дни 14-20

    if days == 0:
        return 1
    elif 1 <= days <= 3:
        return 2
    elif 4 <= days <= 6:
        return 3
    elif days == 7:
        return 4
    elif 8 <= days <= 14:
        return 5
    elif days >= 14:
        return 6

    return user.current_stage


def should_send_reminder(user, days_since_start):
    """
    Определить, нужно ли отправить напоминание пользователю
    на основе триггеров (дней и этапов)

    Args:
        user: объект User
        days_since_start: количество дней с начала практик

    Returns:
        tuple: (should_send: bool, message: str or None)
    """
    current_stage = user.current_stage
    current_step = user.current_step

    # ЭТАП 1 (Посадка) - пользователь сделал посадку (step 6 завершён)
    if current_stage == 1:
        # Если завершил Этап 1 (все 6 шагов) И ещё не нажал кнопку "Всходы появились"
        if current_step >= 6:
            # Проверяем флаг awaiting_sprouts
            # ВАЖНО: Отправляем напоминания ТОЛЬКО если awaiting_sprouts == True
            if not hasattr(user, 'awaiting_sprouts') or not user.awaiting_sprouts:
                # Пользователь уже нажал кнопку, не отправляем напоминания
                return False, None

            # День 2: первое напоминание проверить всходы
            if days_since_start == 2:
                return True, (
                    "🌱 **Пора проверить всходы!**\n\n"
                    "Прошло 2 дня с момента посадки. Обычно в это время появляются первые ростки.\n\n"
                    "Загляните в горшок - видите зелёные петельки? Если да, нажмите кнопку в предыдущем сообщении!\n\n"
                    "Или используйте /status чтобы посмотреть прогресс."
                )
            # День 3: повторное напоминание
            elif days_since_start == 3:
                return True, (
                    "🌿 **Напоминание о всходах**\n\n"
                    "Уже 3 дня с момента посадки. Проверьте горшок - появились ли ростки?\n\n"
                    "Если нет - не переживайте, иногда семенам нужно чуть больше времени.\n\n"
                    "Как только увидите всходы - нажмите кнопку в сообщении выше!"
                )
            # День 4: ещё напоминание
            elif days_since_start == 4:
                return True, (
                    "🌾 **Проверка всходов**\n\n"
                    "4-й день после посадки. Если ростки ещё не показались - проверьте:\n"
                    "• Достаточно ли влаги в почве?\n"
                    "• Накрыт ли горшок плёнкой?\n"
                    "• Стоит ли в тёплом месте?\n\n"
                    "Как только всходы появятся - нажмите кнопку!"
                )
            # День 5: специальное напоминание о пересадке
            elif days_since_start == 5:
                return True, (
                    "⚠️ **Салат не всходит?**\n\n"
                    "Прошло уже 5 дней с момента посадки. Если всходов так и нет, возможно:\n\n"
                    "• Семена оказались невсхожими\n"
                    "• Недостаточно влаги или света\n"
                    "• Слишком глубоко посажены\n\n"
                    "**Рекомендация:** Попробуйте пересадить салат заново:\n"
                    "1. Возьмите новые семена\n"
                    "2. Увлажните почву\n"
                    "3. Посадите неглубоко (1-2 мм)\n"
                    "4. Накройте плёнкой\n\n"
                    "После пересадки используйте /reset чтобы начать отсчёт заново."
                )
        else:
            # Если не завершил Этап 1, напоминаем продолжить
            if days_since_start >= 1:
                return True, (
                    "🌱 **Не забудьте завершить посадку!**\n\n"
                    f"Вы остановились на шаге {current_step} из 6.\n\n"
                    "Завершите первый этап, чтобы начать выращивать ваш салат!\n\n"
                    "/status - продолжить практику"
                )

    # ЭТАП 2 (Всходы) - дни 2-4
    elif current_stage == 2:
        # Если застрял на Этапе 2 больше 2 дней
        if days_since_start >= 5:
            return True, (
                "🌿 **Продолжайте практики!**\n\n"
                "Ваши ростки уже показались? Отлично!\n\n"
                "Переходите к следующему этапу практик.\n\n"
                "/status - посмотреть прогресс"
            )

    # ЭТАП 3 (Практика до микрозелени) - дни 5-7
    elif current_stage == 3:
        if days_since_start == 7:
            return True, (
                "🌱 **Время первого урожая!**\n\n"
                "Прошла неделя с момента посадки. Ваша микрозелень готова к первому сбору!\n\n"
                "Переходите к Этапу 4 - практика «Якорь» и дегустация.\n\n"
                "/status - продолжить"
            )

    # ЭТАП 4 (Первый урожай) - день 7
    elif current_stage == 4:
        if days_since_start >= 8:
            return True, (
                "🌿 **Переходим к росту беби-лифа!**\n\n"
                "Вы попробовали микрозелень? Теперь оставшиеся ростки будут расти дальше.\n\n"
                "Переходите к Этапу 5 - ежедневные практики с большими целями.\n\n"
                "/status - начать Этап 5"
            )

    # ЭТАП 5 (До беби-лифа) - дни 8-14
    elif current_stage == 5:
        # Ежедневные напоминания для Этапа 5 (7 дней)
        day_in_stage = days_since_start - 7  # День внутри Этапа 5
        if 1 <= day_in_stage <= 7:
            return True, (
                f"🌱 **День {day_in_stage} из 7: Ежедневная практика**\n\n"
                f"Продолжайте свои ежедневные практики с большими целями.\n\n"
                f"Ваш беби-лиф растёт, и вместе с ним растут ваши намерения.\n\n"
                "/status - сегодняшняя практика"
            )

    # ЭТАП 6 (Финал) - дни 14-20
    elif current_stage == 6:
        if days_since_start >= 14:
            return True, (
                "🎉 **Финальный этап!**\n\n"
                "Ваш беби-лиф готов к сбору! Время завершить практику и насладиться результатом.\n\n"
                "Переходите к финальным шагам.\n\n"
                "/status - завершить практику"
            )

    return False, None


async def send_practice_reminder(bot: Bot, user_id: int):
    """
    Отправить напоминание о практике пользователю (НОВАЯ ЛОГИКА)

    Args:
        bot: Telegram Bot instance
        user_id: telegram ID пользователя
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            logger.warning(f"Пользователь {user_id} не найден в БД")
            return

        # Проверить, не на паузе ли пользователь
        if user.is_paused:
            logger.info(f"Пользователь {user_id} на паузе, пропускаем напоминание")
            return

        # Рассчитать дни с начала практик
        days = calculate_days_since_start(user)

        # Определить, нужно ли отправить напоминание
        should_send, message = should_send_reminder(user, days)

        if should_send and message:
            # Добавить кнопку в зависимости от этапа
            keyboard = None
            if user.current_stage == 1 and user.current_step >= 6 and 2 <= days <= 5:
                if days == 5:
                    # День 5: две кнопки - всходы появились или салат не взошёл
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Всходы появились!", callback_data="sprouts_appeared")],
                        [InlineKeyboardButton("😔 Салат не взошёл", callback_data="replant_start")]
                    ])
                else:
                    # Дни 2-4: одна кнопка
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ У меня появились первые всходы!", callback_data="sprouts_appeared")]
                    ])
            elif user.current_stage == 6:
                # Финальный этап: кнопка для начала финала
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎉 Приступить к финалу", callback_data="start_stage6_finale")]
                ])

            await bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
            logger.info(f"Отправлено триггерное напоминание пользователю {user_id} (день {days}, этап {user.current_stage})")
        else:
            logger.debug(f"Напоминание не требуется для пользователя {user_id} (день {days}, этап {user.current_stage})")

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания пользователю {user_id}: {e}")
    finally:
        db.close()


async def send_stage4_reminder(bot: Bot, user, db):
    """
    Отправить напоминание о практике Stage 4 (Якорь)

    Args:
        bot: Telegram Bot instance
        user: объект User из БД
        db: сессия БД
    """
    try:
        # Получить Stage 4
        stage = practices_manager.get_stage(4)
        if not stage:
            logger.error("Этап 4 не найден в practices.json")
            return

        # Получить первый шаг Stage 4 (шаг 12)
        steps = stage.get('steps', [])
        if not steps:
            logger.error("Шаги не найдены в Stage 4")
            return

        first_step = steps[0]

        # Обновить состояние пользователя - перевести на Stage 4, Step 12
        from utils.db import update_user_progress
        update_user_progress(db, user.telegram_id, stage_id=4, step_id=12, day=user.current_day)

        # Сбросить daily_practice_day и substep, так как переходим к новому этапу
        user.daily_practice_day = 0
        user.daily_practice_substep = ""
        db.commit()

        logger.info(f"Пользователь {user.telegram_id} переведен на Stage 4, Step 12")

        # Сформировать сообщение-напоминание
        message = f"🌱 **Пора собирать первый урожай!**\n\n"
        message += f"Твоя микрозелень готова! Пришло время практики «Якорь» — мы свяжем твои желания с первыми результатами.\n\n"
        message += f"**{first_step.get('title', '')}**\n\n"
        message += first_step.get('message', '')

        # Создать клавиатуру с кнопкой из практики
        buttons_data = first_step.get('buttons', [])
        keyboard_buttons = []
        if buttons_data:
            for btn in buttons_data:
                keyboard_buttons.append([InlineKeyboardButton(btn['text'], callback_data=btn['action'])])
        else:
            # Если кнопок нет в practice, используем стандартную
            keyboard_buttons.append([InlineKeyboardButton("Начать практику", callback_data="next_step")])

        # Добавить кнопку плесени для Stage 4
        keyboard_buttons.append([InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_sprouts_start")])
        keyboard = InlineKeyboardMarkup(keyboard_buttons)

        # Отправить напоминание
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        logger.info(f"Отправлено напоминание о Stage 4 пользователю {user.telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания Stage 4 пользователю {user.telegram_id}: {e}")


async def send_stage2_sprouts_reminder(bot: Bot, user, db, day: int):
    """
    Отправить напоминание о проверке всходов (Stage 2, дни 2-5)

    Args:
        bot: Telegram Bot
        user: Пользователь из БД
        db: Сессия БД
        day: День (2-5)
    """
    # Тексты сообщений для каждого дня
    messages = {
        2: (
            "🌱 **Пора проверить всходы!**\n\n"
            "Прошло 2 дня с момента посадки. Обычно в это время появляются первые ростки.\n\n"
            "Загляните в горшок - видите зелёные петельки?"
        ),
        3: (
            "🌿 **Напоминание о всходах**\n\n"
            "Уже 3 дня с момента посадки. Проверьте горшок - появились ли ростки?\n\n"
            "Если нет - не переживайте, иногда семенам нужно чуть больше времени."
        ),
        4: (
            "🌾 **Проверка всходов**\n\n"
            "4-й день после посадки. Если ростки ещё не показались - проверьте:\n"
            "• Достаточно ли влаги в почве?\n"
            "• Накрыт ли горшок крышкой?\n"
            "• Стоит ли в тёплом месте?"
        ),
        5: (
            "🌱 **День 5: Проверка всходов**\n\n"
            "Прошло 5 дней с момента посадки. Обычно к этому времени появляются заметные ростки.\n\n"
            "Посмотри в горшок — что ты видишь?"
        )
    }

    message = messages.get(day, messages[2])

    # Кнопки зависят от дня
    if day == 5:
        # День 5: три кнопки (всходы, плесень, не взошёл)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Всходы появились!", callback_data="sprouts_appeared")],
            [InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_start")],
            [InlineKeyboardButton("😔 Салат не взошёл", callback_data="replant_start")]
        ])
    else:
        # Дни 2-4: две кнопки (всходы, плесень)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ У меня появились первые всходы!", callback_data="sprouts_appeared")],
            [InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_start")]
        ])

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=keyboard
        )
        logger.info(f"Отправлено напоминание о всходах (день {day}) пользователю {user.telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания о всходах пользователю {user.telegram_id}: {e}")


async def send_stage6_reminder(bot: Bot, user, db):
    """
    Отправить напоминание о начале финальных практик Stage 6

    Напоминание отправляется один раз на следующий день после завершения Stage 5.
    Пользователь проходит все 7 шагов (24-30) подряд за один раз.
    """
    # Получить Step 24 (первый шаг Stage 6)
    stage = practices_manager.get_stage(6)
    if not stage:
        logger.error("Stage 6 не найден в practices.json")
        return

    steps = stage.get('steps', [])
    first_step = None
    for step in steps:
        if step.get('step_id') == 24:
            first_step = step
            break

    if not first_step:
        logger.error("Step 24 не найден в Stage 6")
        return

    # Сформировать сообщение
    message = "🎉 **Финальный этап!**\n\n"
    message += "Твой беби-лиф готов! Время завершить практику и насладиться результатом.\n\n"
    message += f"**{first_step.get('title', 'Признание мастерства')}**\n\n"
    message += "Сегодня мы пройдём все финальные шаги подряд. Приготовься к празднованию своего успеха! 🌱"

    # Кнопка для начала с Step 24
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Приступить к финалу", callback_data="start_stage6_finale")]
    ])

    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )

        # Очистить stage6_reminder_date после отправки
        user.stage6_reminder_date = None
        db.commit()

        logger.info(f"Отправлено напоминание Stage 6 (финал) пользователю {user.telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка отправки напоминания Stage 6 пользователю {user.telegram_id}: {e}")


async def send_daily_practice_reminder(bot: Bot, user, db):
    """
    Отправить короткое напоминание о ежедневной практике (Stage 3)
    ИЗМЕНЕНО: теперь отправляет только reminder, а не всю практику

    Args:
        bot: Telegram Bot instance
        user: объект User из БД
        db: сессия БД
    """
    try:
        current_day = user.daily_practice_day

        # Получить практику текущего дня
        stage = practices_manager.get_stage(3)
        if not stage:
            logger.error("Этап 3 не найден в practices.json")
            return

        daily_practices = stage.get('daily_practices', [])
        practice = None
        for p in daily_practices:
            if p.get('day') == current_day:
                practice = p
                break

        if not practice:
            logger.error(f"Практика дня {current_day} не найдена в этапе 3")
            return

        # ИЗМЕНЕНИЕ: Получить reminder вместо всей практики
        reminder = practice.get('reminder', {})
        if not reminder:
            logger.error(f"Reminder не найден для дня {current_day}")
            return

        # Сформировать сообщение из reminder
        message = reminder.get('message', '')

        # Создать клавиатуру из reminder.buttons
        buttons = reminder.get('buttons', [])
        keyboard_buttons = []
        for button in buttons:
            text = button.get('text', '')
            action = button.get('action', '')
            if text and action:
                keyboard_buttons.append([InlineKeyboardButton(text, callback_data=action)])

        # Добавить кнопку плесени для Stage 3
        keyboard_buttons.append([InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_sprouts_start")])

        keyboard = InlineKeyboardMarkup(keyboard_buttons) if keyboard_buttons else None

        # Отправить короткое напоминание
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        logger.info(f"Отправлено напоминание (reminder) дня {current_day} пользователю {user.telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания пользователю {user.telegram_id}: {e}")


async def send_stage5_daily_reminder(bot: Bot, user, db):
    """
    Отправить напоминание о ежедневной практике Stage 5 (До беби-лифа)

    Args:
        bot: Telegram Bot instance
        user: объект User из БД
        db: сессия БД
    """
    try:
        current_day = user.daily_practice_day

        # Получить Stage 5
        stage = practices_manager.get_stage(5)
        if not stage:
            logger.error("Этап 5 не найден в practices.json")
            return

        # Получить практику текущего дня
        daily_practices = stage.get('daily_practices', [])
        practice = None
        for p in daily_practices:
            if p.get('day') == current_day:
                practice = p
                break

        if not practice:
            logger.error(f"Практика дня {current_day} не найдена в Stage 5")
            return

        # Сформировать сообщение
        theme = practice.get('theme', '')
        message = f"🌱 **День {current_day} из 7: {theme}**\n\n"
        message += f"Пришло время ежедневной практики с долгосрочными целями.\n\n"
        message += f"Сегодня мы поработаем с темой «{theme}»."

        # Кнопка для начала практики
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Начать практику", callback_data="stage5_start_substep")],
            [InlineKeyboardButton("Напомнить позже", callback_data="postpone_reminder")],
            [InlineKeyboardButton("🍄 Что-то пошло не так / Плесень", callback_data="mold_sprouts_start")]
        ])

        # Отправить напоминание
        await bot.send_message(
            chat_id=user.telegram_id,
            text=message,
            parse_mode='Markdown',
            reply_markup=keyboard
        )

        logger.info(f"Отправлено напоминание Stage 5 (день {current_day}) пользователю {user.telegram_id}")

    except Exception as e:
        logger.error(f"Ошибка при отправке напоминания Stage 5 пользователю {user.telegram_id}: {e}")


async def check_and_send_reminders(bot: Bot):
    """
    Проверить всех пользователей и отправить напоминания тем, кому нужно
    Эта функция вызывается планировщиком каждый час
    """
    from datetime import date as date_class

    db = SessionLocal()
    try:
        # Получить текущее время в UTC
        now_utc = datetime.utcnow()

        # Найти всех активных пользователей, которые начали практики
        users = db.query(User).filter(
            User.is_active == True,
            User.is_paused == False,
            User.started_at.isnot(None)
        ).all()

        logger.info(f"Проверка напоминаний для {len(users)} пользователей")

        for user in users:
            try:
                # Получить часовой пояс пользователя
                user_tz = pytz.timezone(user.timezone)

                # Конвертировать текущее время в часовой пояс пользователя
                now_user_tz = now_utc.replace(tzinfo=pytz.utc).astimezone(user_tz)
                current_hour = now_user_tz.hour
                current_minute = now_user_tz.minute

                # Определить время напоминания: preferred_time или fallback (09:00)
                reminder_time = user.preferred_time or user.reminder_time or "09:00"
                hour, minute = map(int, reminder_time.split(':'))

                # Если текущее время совпадает с временем напоминания (с точностью до часа)
                if current_hour == hour and 0 <= current_minute < 30:
                        # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ STAGE 2: Напоминания о всходах (дни 2-5)
                        if user.current_stage == 1 and user.awaiting_sprouts:
                            # Вычислить день с момента посадки
                            days_since_start = (now_user_tz.date() - user.started_at.replace(tzinfo=pytz.utc).astimezone(user_tz).date()).days

                            # Отправлять напоминания на дни 2, 3, 4, 5
                            if 2 <= days_since_start <= 5:
                                # Проверить, не отправляли ли уже сегодня
                                if user.last_reminder_sent:
                                    last_reminder_user_tz = user.last_reminder_sent.replace(tzinfo=pytz.utc).astimezone(user_tz)
                                    if last_reminder_user_tz.date() == now_user_tz.date():
                                        logger.debug(f"Напоминание о всходах для пользователя {user.telegram_id} уже отправлено сегодня")
                                        continue

                                # Отправить напоминание о всходах
                                await send_stage2_sprouts_reminder(bot, user, db, day=days_since_start)

                                # Обновить время последнего напоминания
                                user.last_reminder_sent = now_utc
                                db.commit()

                                logger.info(f"Отправлено напоминание о всходах (день {days_since_start}) пользователю {user.telegram_id}")
                                continue

                        # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ЕЖЕДНЕВНЫХ ПРАКТИК ЭТАПА 3
                        if user.current_stage == 3 and user.daily_practice_day == 0:
                            # Проверить, не отправляли ли напоминание сегодня
                            # (чтобы Stage 3 уведомление пришло на СЛЕДУЮЩИЙ день после завершения Stage 2)
                            if user.last_reminder_sent:
                                last_reminder_user_tz = user.last_reminder_sent.replace(tzinfo=pytz.utc).astimezone(user_tz)
                                if last_reminder_user_tz.date() == now_user_tz.date():
                                    logger.debug(f"Пользователь {user.telegram_id} перешёл на Stage 3 сегодня, ждём завтра")
                                    continue

                            # Пользователь в режиме ожидания, нужно начать первую практику
                            user.daily_practice_day = 1
                            db.commit()

                            # Отправить первую ежедневную практику
                            await send_daily_practice_reminder(bot, user, db)

                            # Обновить время последнего напоминания
                            user.last_reminder_sent = now_utc
                            db.commit()
                            continue

                        if user.current_stage == 3 and user.daily_practice_day >= 1:
                            # Проверить, не выполнена ли уже практика сегодня
                            today_str = now_user_tz.date().strftime('%Y-%m-%d')

                            if user.last_practice_date == today_str:
                                logger.debug(f"Пользователь {user.telegram_id} уже выполнил практику сегодня")
                                continue

                            # Проверить отложенное напоминание
                            if user.reminder_postponed and user.postponed_until:
                                # Если время ещё не пришло, пропускаем
                                if now_utc < user.postponed_until:
                                    logger.debug(f"Напоминание для пользователя {user.telegram_id} отложено до {user.postponed_until}")
                                    continue

                            # Отправить ежедневную практику
                            await send_daily_practice_reminder(bot, user, db)

                            # Обновить время последнего напоминания
                            user.last_reminder_sent = now_utc
                            db.commit()
                            continue

                        # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ НАПОМИНАНИЯ О STAGE 4 (практика "Якорь")
                        if user.stage4_reminder_date:
                            today_str = now_user_tz.date().strftime('%Y-%m-%d')

                            # Если сегодня день напоминания о Stage 4
                            if user.stage4_reminder_date == today_str:
                                # Отправить напоминание о Stage 4
                                await send_stage4_reminder(bot, user, db)

                                # Сбросить флаг напоминания
                                user.stage4_reminder_date = None

                                # Обновить время последнего напоминания
                                user.last_reminder_sent = now_utc
                                db.commit()

                                logger.info(f"Отправлено напоминание о Stage 4 пользователю {user.telegram_id}")
                                continue

                        # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ НАПОМИНАНИЯ О STAGE 6 (Финальный этап)
                        if user.stage6_reminder_date:
                            today_str = now_user_tz.date().strftime('%Y-%m-%d')

                            # Если сегодня день напоминания о Stage 6
                            if user.stage6_reminder_date == today_str:
                                # Отправить напоминание о Stage 6
                                await send_stage6_reminder(bot, user, db)

                                # Обновить время последнего напоминания
                                user.last_reminder_sent = now_utc
                                db.commit()

                                logger.info(f"Отправлено напоминание о Stage 6 пользователю {user.telegram_id}")
                                continue

                        # СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ЕЖЕДНЕВНЫХ ПРАКТИК STAGE 5 (До беби-лифа)
                        if user.current_stage == 5 and user.daily_practice_day == 0:
                            # Пользователь в режиме ожидания, нужно начать первую практику
                            user.daily_practice_day = 1
                            db.commit()

                            # Отправить первую практику Stage 5
                            await send_stage5_daily_reminder(bot, user, db)

                            # Обновить время последнего напоминания
                            user.last_reminder_sent = now_utc
                            db.commit()
                            continue

                        if user.current_stage == 5 and user.daily_practice_day >= 1:
                            # Проверить, не выполнена ли уже практика сегодня
                            today_str = now_user_tz.date().strftime('%Y-%m-%d')

                            if user.last_practice_date == today_str:
                                logger.debug(f"Пользователь {user.telegram_id} уже выполнил практику Stage 5 сегодня")
                                continue

                            # Проверить отложенное напоминание
                            if user.reminder_postponed and user.postponed_until:
                                # Если время ещё не пришло, пропускаем
                                if now_utc < user.postponed_until:
                                    logger.debug(f"Напоминание Stage 5 для пользователя {user.telegram_id} отложено до {user.postponed_until}")
                                    continue

                            # Отправить ежедневную практику Stage 5
                            await send_stage5_daily_reminder(bot, user, db)

                            # Обновить время последнего напоминания
                            user.last_reminder_sent = now_utc
                            db.commit()
                            continue

                        # Проверить, не отправляли ли уже сегодня (для обычных напоминаний)
                        if user.last_reminder_sent:
                            last_reminder_date = user.last_reminder_sent.date()
                            today = now_user_tz.date()

                            if last_reminder_date == today:
                                logger.debug(f"Пользователю {user.telegram_id} уже отправлено напоминание сегодня")
                                continue

                        # Рассчитать дни с начала практик
                        days = calculate_days_since_start(user)

                        # Проверить, нужно ли отправить напоминание (триггерная система)
                        should_send, _ = should_send_reminder(user, days)

                        if should_send:
                            # Отправить напоминание
                            await send_practice_reminder(bot, user.telegram_id)

                            # Обновить время последнего напоминания
                            user.last_reminder_sent = now_utc
                            db.commit()
                        else:
                            logger.debug(f"Триггер не сработал для пользователя {user.telegram_id} (день {days}, этап {user.current_stage})")

            except Exception as e:
                logger.error(f"Ошибка при обработке пользователя {user.telegram_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Ошибка в check_and_send_reminders: {e}")
    finally:
        db.close()


def schedule_user_reminders(bot: Bot):
    """
    Настроить планировщик для проверки напоминаний каждый час

    Args:
        bot: Telegram Bot instance
    """
    # Запускать проверку каждый час (в начале часа)
    scheduler.add_job(
        check_and_send_reminders,
        CronTrigger(minute=0),  # Каждый час в 00 минут
        args=[bot],
        id='check_reminders',
        replace_existing=True
    )
    logger.info("✅ Планировщик настроен: проверка каждый час в 00 минут")


def schedule_daily_stage5_practices(bot: Bot):
    """
    Настроить ежедневные практики для Этапа 5
    Отправляет практику каждый день пользователям на Этапе 5
    """
    # TODO: Реализовать в следующем этапе
    pass
