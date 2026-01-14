"""
Скрипт для тестирования системы напоминаний
Позволяет изменить started_at на прошлую дату для симуляции дней
"""
import sys
from datetime import datetime, timedelta
from models import SessionLocal, User

def show_users():
    """Показать всех пользователей"""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"\n{'='*80}")
        print(f"Всего пользователей: {len(users)}")
        print(f"{'='*80}\n")

        for user in users:
            print(f"ID: {user.telegram_id}")
            print(f"Имя: {user.first_name} (@{user.username})")
            print(f"Этап: {user.current_stage}, Шаг: {user.current_step}")
            print(f"Создан: {user.created_at}")
            print(f"Начал практики: {user.started_at}")
            print(f"Время напоминаний: {user.preferred_time}")
            print(f"Часовой пояс: {user.timezone}")

            if user.started_at:
                days = (datetime.utcnow() - user.started_at).days
                print(f"📅 Дней с начала: {days}")

            print(f"{'-'*80}\n")
    finally:
        db.close()


def simulate_day(user_id, days_ago):
    """
    Симулировать день, установив started_at на N дней назад

    Args:
        user_id: telegram ID пользователя
        days_ago: сколько дней назад (например, 2 = 2 дня назад)
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()

        if not user:
            print(f"❌ Пользователь {user_id} не найден!")
            return

        # Установить started_at на N дней назад
        new_started_at = datetime.utcnow() - timedelta(days=days_ago)
        user.started_at = new_started_at

        # Также установить preferred_time на текущее время +1 минута (для быстрого теста)
        current_time = datetime.now()
        test_time = (current_time + timedelta(minutes=1)).strftime("%H:%M")
        user.preferred_time = test_time

        db.commit()

        print(f"\n✅ СИМУЛЯЦИЯ УСТАНОВЛЕНА:")
        print(f"   Пользователь: {user.first_name} ({user_id})")
        print(f"   Started_at: {new_started_at} (UTC)")
        print(f"   Это симулирует День {days_ago}")
        print(f"   Preferred_time установлено на: {test_time}")
        print(f"   Текущий этап: {user.current_stage}, Шаг: {user.current_step}")
        print(f"\n⏰ Напоминание придёт в {test_time} (через ~1 минуту)")
        print(f"   Проверьте Telegram!\n")

    finally:
        db.close()


def reset_time(user_id):
    """Сбросить время напоминаний пользователя"""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.telegram_id == user_id).first()
        if user:
            user.preferred_time = None
            user.last_reminder_sent = None
            db.commit()
            print(f"✅ Время напоминаний сброшено для пользователя {user_id}")
    finally:
        db.close()


if __name__ == "__main__":
    print("\n🧪 ТЕСТИРОВАНИЕ СИСТЕМЫ НАПОМИНАНИЙ\n")

    if len(sys.argv) < 2:
        print("Использование:")
        print("  python test_reminders.py show              - показать всех пользователей")
        print("  python test_reminders.py simulate USER_ID DAYS  - симулировать день")
        print("\nПримеры:")
        print("  python test_reminders.py show")
        print("  python test_reminders.py simulate 1585940117 2   - День 2 (проверить всходы)")
        print("  python test_reminders.py simulate 1585940117 5   - День 5 (критическое напоминание)")
        sys.exit(0)

    command = sys.argv[1]

    if command == "show":
        show_users()

    elif command == "simulate":
        if len(sys.argv) < 4:
            print("❌ Нужно указать USER_ID и количество дней!")
            print("Пример: python test_reminders.py simulate 1585940117 2")
            sys.exit(1)

        user_id = int(sys.argv[2])
        days = int(sys.argv[3])
        simulate_day(user_id, days)

    else:
        print(f"❌ Неизвестная команда: {command}")
        print("Используйте: show или simulate")
