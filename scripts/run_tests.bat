@echo off
echo ========================================
echo Sogreto Bot - Running tests
echo ========================================
echo.

echo Running pytest...
python -m pytest tests/ -v --tb=short

echo.
echo ========================================
if %errorlevel% equ 0 (
    echo All tests passed successfully!
) else (
    echo Some tests failed
)
echo ========================================
echo.
pause
