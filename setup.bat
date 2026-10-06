@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt

if not exist .env (
    copy .env.example .env >nul
    echo تم إنشاء ملف .env من .env.example
)

echo.
echo تم تجهيز المشروع بنجاح.
echo الخطوة التالية:
echo 1^) افتح ملف .env وضع TELEGRAM_BOT_TOKEN
echo 2^) فعّل البيئة: .venv\Scripts\activate
echo 3^) شغّل البوت: python bot.py
