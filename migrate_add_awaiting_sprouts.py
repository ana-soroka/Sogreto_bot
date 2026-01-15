"""
Миграция: добавление поля awaiting_sprouts в таблицу users
"""
from models import engine
from sqlalchemy import text

def migrate():
    """Добавить поле awaiting_sprouts если его нет"""
    with engine.connect() as conn:
        # Проверяем, есть ли уже это поле
        result = conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]

        if 'awaiting_sprouts' not in columns:
            print("Добавляем поле awaiting_sprouts...")
            conn.execute(text("ALTER TABLE users ADD COLUMN awaiting_sprouts BOOLEAN DEFAULT 0"))
            conn.commit()
            print("✅ Поле awaiting_sprouts добавлено успешно!")
        else:
            print("⚠️ Поле awaiting_sprouts уже существует, пропускаем миграцию")

if __name__ == "__main__":
    migrate()
