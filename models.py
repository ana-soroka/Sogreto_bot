"""
Модели базы данных для Sogreto Bot
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///sogreto_bot.db')

# Railway использует postgres://, но SQLAlchemy требует postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Создание движка БД
engine = create_engine(
    DATABASE_URL,
    echo=False,  # Отключить логи SQL в продакшене
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith('sqlite') else {}
)

# Фабрика сессий
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class User(Base):
    """Модель пользователя бота"""
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)

    # Прогресс практик
    current_stage = Column(Integer, default=1)  # Текущий этап (1-6)
    current_step = Column(Integer, default=1)   # Текущий шаг внутри этапа
    current_day = Column(Integer, default=1)     # День практики (1-20)

    # Статус
    is_active = Column(Boolean, default=True)
    is_paused = Column(Boolean, default=False)
    awaiting_sprouts = Column(Boolean, default=False)  # Ожидание всходов после этапа 1

    # Ежедневные практики (Stage 3)
    daily_practice_day = Column(Integer, default=0)  # 0 = ожидание, 1-4 = дни практик
    daily_practice_substep = Column(String(20), default="")  # Текущий подшаг: "intro", "practice", "checkin", "response_A", "response_B", "completion"
    last_practice_date = Column(String(10), nullable=True)  # YYYY-MM-DD формат
    reminder_postponed = Column(Boolean, default=False)  # Напоминание отложено
    postponed_until = Column(DateTime, nullable=True)  # Время отложенного напоминания

    # Stage 4 напоминание (практика "Якорь")
    stage4_reminder_date = Column(String(10), nullable=True)  # YYYY-MM-DD формат, дата напоминания о Stage 4

    # Stage 6 напоминание (финальный этап)
    stage6_reminder_date = Column(String(10), nullable=True)  # YYYY-MM-DD формат

    # Настройки
    timezone = Column(String(50), default='Europe/Moscow')
    reminder_time = Column(String(5), default='09:00')  # Старое поле (deprecated)
    preferred_time = Column(String(5), nullable=True)   # Время напоминаний HH:MM

    # Временные метки
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    last_interaction = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)  # Когда пользователь начал практики
    last_reminder_sent = Column(DateTime, nullable=True)  # Последнее отправленное напоминание
    paused_at = Column(DateTime, nullable=True)
    resumed_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, stage={self.current_stage}, day={self.current_day})>"


class UserProgress(Base):
    """История прохождения практик пользователем"""
    __tablename__ = 'user_progress'

    id = Column(Integer, primary_key=True, index=True)
    user_telegram_id = Column(Integer, nullable=False, index=True)

    # Какой этап/шаг пройден
    stage_id = Column(Integer, nullable=False)
    step_id = Column(Integer, nullable=False)
    day = Column(Integer, nullable=False)

    # Ответы пользователя (если есть)
    user_response = Column(Text, nullable=True)

    # Временные метки
    completed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<UserProgress(user={self.user_telegram_id}, stage={self.stage_id}, step={self.step_id})>"


class ScheduledReminder(Base):
    """Запланированные напоминания (для APScheduler)"""
    __tablename__ = 'scheduled_reminders'

    id = Column(Integer, primary_key=True, index=True)
    user_telegram_id = Column(Integer, nullable=False, index=True)

    # Тип напоминания
    reminder_type = Column(String(50), nullable=False)  # 'daily', 'next_practice', 'custom'

    # Когда отправить
    scheduled_time = Column(DateTime, nullable=False)

    # Статус
    is_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)

    # Содержание
    message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<ScheduledReminder(user={self.user_telegram_id}, type={self.reminder_type}, time={self.scheduled_time})>"


def init_db():
    """Инициализация базы данных - создание всех таблиц"""
    Base.metadata.create_all(bind=engine)
    print("OK: База данных инициализирована")


def get_db():
    """Получить сессию БД (для использования в handlers)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Создание таблиц при импорте модуля
if __name__ == "__main__":
    print("Создание таблиц базы данных...")
    init_db()
    print("Готово!")
