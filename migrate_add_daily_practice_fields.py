# -*- coding: utf-8 -*-
"""
Миграция: Добавление полей для ежедневных практик (Stage 3)

Добавляет новые поля в таблицу users:
- daily_practice_day: день ежедневной практики (0 = ожидание, 1-4 = дни)
- last_practice_date: дата последней выполненной практики
- reminder_postponed: флаг отложенного напоминания
- postponed_until: время отложенного напоминания
"""

import sqlite3
import sys
from datetime import datetime

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DATABASE_URL = 'sogreto_bot.db'


def migrate():
    """Применить миграцию"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        # Проверяем, существуют ли уже поля
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        # Добавляем новые поля, если их еще нет
        if 'daily_practice_day' not in columns:
            print("Добавление поля daily_practice_day...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_practice_day INTEGER DEFAULT 0")
            print("[OK] Поле daily_practice_day добавлено")
        else:
            print("[SKIP] Поле daily_practice_day уже существует")

        if 'last_practice_date' not in columns:
            print("Добавление поля last_practice_date...")
            cursor.execute("ALTER TABLE users ADD COLUMN last_practice_date TEXT")
            print("[OK] Поле last_practice_date добавлено")
        else:
            print("[SKIP] Поле last_practice_date уже существует")

        if 'reminder_postponed' not in columns:
            print("Добавление поля reminder_postponed...")
            cursor.execute("ALTER TABLE users ADD COLUMN reminder_postponed INTEGER DEFAULT 0")
            print("[OK] Поле reminder_postponed добавлено")
        else:
            print("[SKIP] Поле reminder_postponed уже существует")

        if 'postponed_until' not in columns:
            print("Добавление поля postponed_until...")
            cursor.execute("ALTER TABLE users ADD COLUMN postponed_until TEXT")
            print("[OK] Поле postponed_until добавлено")
        else:
            print("[SKIP] Поле postponed_until уже существует")

        # Применяем изменения
        conn.commit()
        print("\n[SUCCESS] Миграция успешно завершена!")

    except sqlite3.Error as e:
        print(f"\n[ERROR] Ошибка миграции: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    print("=" * 50)
    print("Миграция: Добавление полей для ежедневных практик")
    print("=" * 50)
    print(f"Время запуска: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    migrate()

    print()
    print("=" * 50)
