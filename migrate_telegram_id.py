"""
Миграция: изменить telegram_id с INTEGER на BIGINT
Запустить один раз на Railway: python migrate_telegram_id.py
"""
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', '')

if not DATABASE_URL:
    print("ERROR: DATABASE_URL не задан")
    exit(1)

# Railway использует postgres://, но SQLAlchemy требует postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

print(f"Подключение к базе данных...")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # Изменить тип колонки telegram_id на BIGINT во всех таблицах
    print("Изменение telegram_id с INTEGER на BIGINT...")

    conn.execute(text("ALTER TABLE users ALTER COLUMN telegram_id TYPE BIGINT"))
    print("  - users.telegram_id: OK")

    conn.execute(text("ALTER TABLE user_progress ALTER COLUMN user_telegram_id TYPE BIGINT"))
    print("  - user_progress.user_telegram_id: OK")

    conn.execute(text("ALTER TABLE scheduled_reminders ALTER COLUMN user_telegram_id TYPE BIGINT"))
    print("  - scheduled_reminders.user_telegram_id: OK")

    conn.commit()
    print("\nМиграция завершена успешно!")
