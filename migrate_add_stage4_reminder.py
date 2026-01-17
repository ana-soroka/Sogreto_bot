"""
Миграция: добавить поле stage4_reminder_date в таблицу users
"""
import sqlite3

DATABASE_URL = 'sogreto_bot.db'

def migrate():
    conn = sqlite3.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        # Проверить наличие поля
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'stage4_reminder_date' not in columns:
            print("Добавление поля stage4_reminder_date...")
            cursor.execute("ALTER TABLE users ADD COLUMN stage4_reminder_date TEXT")
            conn.commit()
            print("[OK] Поле stage4_reminder_date добавлено")
        else:
            print("[SKIP] Поле stage4_reminder_date уже существует")

    except Exception as e:
        print(f"[ERROR] {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
