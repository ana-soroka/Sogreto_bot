@echo off
echo ========================================
echo Sogreto Bot - Starting
echo ========================================
echo.

REM Check .env file exists
if not exist .env (
    echo ERROR: .env file not found!
    echo Create .env file with your bot token
    pause
    exit /b 1
)

REM Check practices.json exists
if not exist practices.json (
    echo ERROR: practices.json not found!
    pause
    exit /b 1
)

REM Initialize DB if not exists
if not exist sogreto_bot.db (
    echo Initializing database...
    python models.py
    echo.
)

echo Starting bot...
echo Press Ctrl+C to stop
echo.
python bot.py

pause
