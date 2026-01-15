# -*- coding: utf-8 -*-
"""
Миграция: добавить поле daily_practice_substep в таблицу users
"""
import sqlite3
import sys

# Настройка кодировки для Windows
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

DATABASE_URL = 'sogreto_bot.db'


def migrate():
    """Применить миграцию"""
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        # Проверить наличие поля
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'daily_practice_substep' not in columns:
            print("Добавление поля daily_practice_substep...")
            cursor.execute("ALTER TABLE users ADD COLUMN daily_practice_substep TEXT DEFAULT ''")
            conn.commit()
            print("[OK] Поле daily_practice_substep добавлено")
        else:
            print("[SKIP] Поле daily_practice_substep уже существует")

        print("\n[SUCCESS] Миграция успешно завершена!")

    except sqlite3.Error as e:
        print(f"\n[ERROR] Ошибка миграции: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
