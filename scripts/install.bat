@echo off
echo ========================================
echo Sogreto Bot - Installing dependencies
echo ========================================
echo.

echo [1/4] Checking Python...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python not found!
    echo Install Python from python.org
    pause
    exit /b 1
)
echo.

echo [2/4] Checking pip...
python -m pip --version
if %errorlevel% neq 0 (
    echo ERROR: pip not found!
    pause
    exit /b 1
)
echo.

echo [3/4] Installing dependencies...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR during installation!
    pause
    exit /b 1
)
echo.

echo [4/4] Checking installation...
python check_setup.py
if %errorlevel% neq 0 (
    echo Some dependencies not installed.
    echo Try: python -m pip install -r requirements.txt --force-reinstall
    pause
    exit /b 1
)
echo.

echo ========================================
echo Installation completed successfully!
echo ========================================
echo.
echo Next steps:
echo 1. Check token in .env file
echo 2. Initialize DB: python models.py
echo 3. Run tests: python -m pytest tests/ -v
echo 4. Run bot: python bot.py
echo.
pause
