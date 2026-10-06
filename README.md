# Telegram Bot - تشغيل محلي بسهولة

هذا المشروع عبارة عن بوت تيليجرام يعمل محلياً على جهازك باستخدام Python.  
الهدف من هذا الدليل أن تشغّل البوت بدون تعقيد، سواء على **macOS / Linux** أو **Windows**.

## المتطلبات

- Python 3.11 أو أحدث
- حساب تيليجرام
- توكن البوت من [@BotFather](https://t.me/BotFather)

## الحصول على `TELEGRAM_BOT_TOKEN` من @BotFather

1. افتح تيليجرام وابحث عن [@BotFather](https://t.me/BotFather).
2. أرسل الأمر `/start`.
3. إذا لم يكن لديك بوت، أرسل `/newbot`.
4. اختر اسم البوت الظاهر للمستخدمين.
5. اختر **username** ينتهي بـ `bot`.
6. سيرسل لك BotFather رسالة تحتوي على **Token**.
7. انسخ التوكن وضعه داخل ملف `.env` في المتغير:

```env
TELEGRAM_BOT_TOKEN=ضع_التوكن_هنا
```

> مهم: لا تشارك التوكن مع أي شخص، ولا ترفعه إلى GitHub.

## التشغيل السريع

### macOS / Linux

```bash
chmod +x setup.sh
./setup.sh
```

### Windows

شغّل الملف التالي بالنقر المزدوج أو من `cmd`:

```bat
setup.bat
```

بعد انتهاء التثبيت:

1. افتح ملف `.env`
2. ضع قيمة `TELEGRAM_BOT_TOKEN`
3. شغّل البوت

#### macOS / Linux

```bash
source .venv/bin/activate
python bot.py
```

#### Windows

```bat
call .venv\Scripts\activate.bat
python bot.py
```

## التشغيل اليدوي خطوة بخطوة

إذا كنت لا تريد استخدام ملفات الإعداد الجاهزة:

### 1) تنزيل المشروع

```bash
git clone https://github.com/z2585y8btd-stack/Telegram-bot.git
cd Telegram-bot
```

### 2) إنشاء بيئة افتراضية

#### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows

```bat
python -m venv .venv
call .venv\Scripts\activate.bat
```

### 3) تثبيت المتطلبات

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4) تجهيز ملف البيئة

انسخ الملف المثال:

```bash
cp .env.example .env
```

على Windows:

```bat
copy .env.example .env
```

ثم عدّل `.env` وضع القيم المناسبة.

### 5) تشغيل البوت

```bash
python bot.py
```

إذا كان كل شيء صحيحاً سيبدأ البوت بالعمل بنظام **polling** محلياً من جهازك.

## جميع متغيرات البيئة

| المتغير | مطلوب؟ | الوصف |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | نعم | توكن البوت من @BotFather. يدعم أيضاً `BOT_TOKEN` و `TELEGRAM_TOKEN`. |
| `OPENAI_API_KEY` | لا | مفتاح OpenAI. إذا تركته فارغاً سيعمل البوت بردود محلية مدمجة فقط. |
| `OPENAI_MODEL` | لا | موديل OpenAI المستخدم. الافتراضي `gpt-4o-mini`. |
| `BOT_ADMIN_ID` | لا | رقم Telegram User ID للأدمن المسموح له بأوامر الإدارة. يدعم أيضاً `ADMIN_ID`. |
| `USER_STORE_FILE` | لا | اسم ملف التخزين المحلي للمستخدمين والمدفوعات. الافتراضي `bot_users.json`. يدعم أيضاً `BOT_USER_STORE_FILE`. |

## مثال ملف `.env`

```env
TELEGRAM_BOT_TOKEN=1234567890:your_bot_token_here
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
BOT_ADMIN_ID=8561249287
USER_STORE_FILE=bot_users.json
```

## أوامر البوت

### `/start`
- يبدأ المحادثة مع البوت
- يعرض رسالة الترحيب
- يعرض زر **Private Channel ®️**

### `/channel`
- يرسل رابط القناة العامة

### `/subscribe`
- يرسل فاتورة اشتراك القناة الخاصة
- قيمة الاشتراك الحالية: **1800 Telegram Stars**

### `/rename`
- **للأدمن فقط**
- يغيّر اسم مستخدم محفوظ داخل التخزين المحلي
- الصيغة:

```text
/rename <رقم الشخص أو ID> <الاسم الجديد>
```

### `/people`
- **للأدمن فقط**
- يعرض الأشخاص المسجلين داخل التخزين المحلي مع أرقامهم ومعرفاتهم

## كيف يعمل الدفع والاشتراك؟

البوت يحتوي على اشتراك لقناة خاصة عبر **Telegram Stars**:

1. المستخدم يضغط زر **Private Channel ®️** أو يرسل `/subscribe`
2. البوت يرسل فاتورة دفع داخل تيليجرام
3. العملة المستخدمة هي `XTR` (Telegram Stars)
4. قيمة الاشتراك الحالية هي **1800 نجمة**
5. بعد نجاح الدفع، البوت:
   - يسجل عملية الدفع داخل ملف التخزين المحلي
   - يرسل زر **Join** للوصول إلى القناة الخاصة

> ملاحظة: في الوضع الحالي لا توجد متغيرات بيئية إضافية خاصة بالدفع؛ يكفي تشغيل البوت بالتوكن الصحيح، ثم تتم الفاتورة عبر Telegram Stars من داخل تيليجرام.

### أين يتم حفظ بيانات الدفع؟

محلياً داخل الملف المحدد في:

```env
USER_STORE_FILE=bot_users.json
```

ويتم فيه حفظ:
- المستخدمين
- الرسائل الإدارية
- المدفوعات الناجحة

## ملاحظات مهمة

- إذا لم تضف `OPENAI_API_KEY` فالبوت **سيعمل بشكل طبيعي** بردود محلية جاهزة.
- إذا ظهر خطأ متعلق بالتوكن، تأكد أن `TELEGRAM_BOT_TOKEN` صحيح داخل `.env`.
- أوامر الإدارة لن تعمل إلا للحساب الذي يطابق `BOT_ADMIN_ID`.
- يجب أن تبقي الجهاز مشغلاً طالما تريد البوت أن يبقى شغالاً محلياً.

## إيقاف البوت

اضغط:

```text
Ctrl + C
```

داخل نافذة التشغيل.
