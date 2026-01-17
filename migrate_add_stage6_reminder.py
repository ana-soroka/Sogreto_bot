"""
Миграция: добавление поля stage6_reminder_date в таблицу users
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from models import User
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///sogreto.db')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def migrate():
    print("Начинаем миграцию: добавление stage6_reminder_date...")

    db = SessionLocal()
    try:
        # Проверяем наличие колонки
        db.execute(text("SELECT stage6_reminder_date FROM users LIMIT 1"))
        print("Колонка stage6_reminder_date уже существует.")
        return
    except Exception:
        print("Колонка не найдена. Добавляем...")

    # Добавляем колонку
    try:
        db.execute(text("ALTER TABLE users ADD COLUMN stage6_reminder_date VARCHAR(10)"))
        db.commit()
        print("OK: Колонка stage6_reminder_date успешно добавлена!")
    except Exception as e:
        print(f"ERROR: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    migrate()
