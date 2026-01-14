# Быстрый старт Sogreto Bot

## Шаг 1: Установка Python

⚠️ **Важно:** Если у вас Python установлен через Microsoft Store, удалите его.

1. Скачайте Python 3.9+ с [python.org](https://www.python.org/downloads/)
2. При установке **обязательно** отметьте "Add Python to PATH"
3. Проверьте установку в PowerShell:
   ```powershell
   python --version
   ```

## Шаг 2: Установка зависимостей

### Вариант А: Автоматическая установка (рекомендуется)

Просто запустите файл:
```
install.bat
```

### Вариант Б: Ручная установка

Откройте PowerShell или CMD в папке проекта:

```powershell
python -m pip install -r requirements.txt
python check_setup.py
```

Должно появиться:
```
✅ Все зависимости установлены!
```

## Шаг 3: Проверка токена

Убедитесь что в файле `.env` указан ваш токен:
```
TELEGRAM_BOT_TOKEN=ваш_токен_здесь
```

## Шаг 4: Запуск тестов (опционально)

Запустите файл:
```
run_tests.bat
```

Или вручную:
```powershell
python -m pytest tests/ -v
```

## Шаг 5: Запуск бота

### Вариант А: Автоматический запуск (рекомендуется)

Просто запустите:
```
run_bot.bat
```

Бот автоматически:
- Создаст базу данных (если нужно)
- Запустится и будет ждать сообщений

### Вариант Б: Ручной запуск

```powershell
python models.py    # Создать БД (первый раз)
python bot.py       # Запустить бота
```

Вы увидите:
```
Sogreto Bot запускается...
Бот запущен! Нажмите Ctrl+C для остановки.
```

## Шаг 6: Тестирование в Telegram

1. Откройте Telegram
2. Найдите своего бота (имя которое вы указали в BotFather)
3. Отправьте `/start`
4. Попробуйте команды:
   - `/help` - справка
   - `/status` - прогресс
   - `/contact` - контакты

## Возможные проблемы

### "Python не найден"
- Переустановите Python с python.org
- Отметьте "Add to PATH" при установке

### "pip не найден"
```powershell
python -m ensurepip --upgrade
```

### "ModuleNotFoundError"
```powershell
python -m pip install -r requirements.txt --force-reinstall
```

### Бот не отвечает
1. Проверьте токен в `.env`
2. Проверьте что бот запущен (не выдаёт ошибок)
3. Проверьте логи: `logs/bot.log`

## Следующие шаги

После успешного запуска базовой версии:
1. Добавить команду `/start_practice`
2. Реализовать отправку практик
3. Настроить планировщик напоминаний
4. Добавить команды `/pause`, `/resume`, `/reset`

---

Нужна помощь? Проверьте [README.md](README.md) или [docs/CRITICAL_REVIEW.md](docs/CRITICAL_REVIEW.md)
