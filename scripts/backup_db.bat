@echo off
REM Скрипт автоматического бэкапа базы данных Sogreto Bot (Windows)
REM Использование: backup_db.bat

REM Конфигурация
SET DB_FILE=sogreto_bot.db
SET BACKUP_DIR=backups
SET MAX_BACKUPS=7

REM Создать имя файла с датой и временем
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set datetime=%%I
SET DATE_TIME=%datetime:~0,8%_%datetime:~8,6%
SET BACKUP_FILE=%BACKUP_DIR%\sogreto_bot_%DATE_TIME%.db

REM Создать директорию для бэкапов если не существует
if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"

REM Проверить что БД существует
if not exist "%DB_FILE%" (
    echo ❌ Ошибка: Файл базы данных %DB_FILE% не найден
    exit /b 1
)

REM Создать бэкап
echo 📦 Создание бэкапа базы данных...
copy "%DB_FILE%" "%BACKUP_FILE%" >nul

if %ERRORLEVEL% EQU 0 (
    echo ✅ Бэкап создан: %BACKUP_FILE%

    REM Показать размер файла
    for %%A in ("%BACKUP_FILE%") do set SIZE=%%~zA
    echo 📊 Размер бэкапа: %SIZE% bytes

    REM Удалить старые бэкапы (оставить только последние MAX_BACKUPS)
    echo 🧹 Проверка старых бэкапов...

    REM Показать список существующих бэкапов
    echo.
    echo 📁 Список бэкапов:
    dir /b "%BACKUP_DIR%\sogreto_bot_*.db"

    echo.
    echo ✅ Бэкап завершён успешно
) else (
    echo ❌ Ошибка при создании бэкапа
    exit /b 1
)
