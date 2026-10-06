#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python غير موجود. ثبّت Python 3.11 أو أحدث ثم أعد المحاولة."
  exit 1
fi

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "تم إنشاء ملف .env من .env.example"
fi

echo
echo "تم تجهيز المشروع بنجاح."
echo "الخطوة التالية:"
echo "1) افتح ملف .env وضع TELEGRAM_BOT_TOKEN"
echo "2) فعّل البيئة: source .venv/bin/activate"
echo "3) شغّل البوت: python bot.py"
