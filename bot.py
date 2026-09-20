import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, PreCheckoutQueryHandler, filters,
)

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ADMIN_ID = int(os.getenv("BOT_ADMIN_ID", "8561249287"))
USER_STORE_FILE = Path(os.getenv("USER_STORE_FILE", "bot_users.json"))
CHANNEL_URL = "https://t.me/+LIVzUK7_TxphNGZk"
CONTACT_ADMIN_CALLBACK = "contact_admin"
SNAPCHAT_CALLBACK = "buy_snapchat"
SNAPCHAT_USERNAME = "Sela.mon"
SNAPCHAT_PRICE = 250
SNAPCHAT_PAYLOAD_PREFIX = "snapchat_250_stars"
MAX_HISTORY_MESSAGES = 20
OPENAI_QUOTA_ERROR_CODES = {"insufficient_quota", "credit_balance_exhausted"}

SYSTEM_PROMPT = """أنت مساعد تيليجرام سعودي ذكي ولطيف وخفيف دم.
أجب باللهجة السعودية إذا كان المستخدم يتحدث بالعربية، وكن مفيدًا ولطيفًا.
إذا سأل المستخدم وش نوعك أو ما نوعك فأجب حرفيًا: انا بوت اقصد بوث 😝.
لا تستخدم محتوى جنسيًا صريحًا أو يستغل القاصرين أو يتضمن إكراهًا."""

client: Optional[AsyncOpenAI] = None
if OPENAI_API_KEY and AsyncOpenAI:
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=45.0, max_retries=2)


def load_store() -> dict[str, Any]:
    default = {"next_person": 1, "users": {}, "admin_messages": {}, "payments": []}
    try:
        if USER_STORE_FILE.exists():
            default.update(json.loads(USER_STORE_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not load user store")
    default.setdefault("payments", [])
    return default


STORE = load_store()


def save_store() -> None:
    temporary = USER_STORE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(STORE, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(USER_STORE_FILE)


def display_name(record: dict[str, Any]) -> str:
    return record.get("name") or f"شخص {record['person_number']}"


def user_record(user_id: int, user: Any) -> dict[str, Any]:
    key = str(user_id)
    record = STORE["users"].get(key)
    if not record:
        number = int(STORE["next_person"])
        STORE["next_person"] = number + 1
        record = {"person_number": number, "name": f"شخص {number}", "user_id": user_id}
        STORE["users"][key] = record
    record["username"] = user.username or ""
    record["first_name"] = user.first_name or ""
    save_store()
    return record


def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 انضم الآن إلى القناة", url=CHANNEL_URL)],
        [InlineKeyboardButton("Snapchat 👻 — 250 ⭐️", callback_data=SNAPCHAT_CALLBACK)],
        [InlineKeyboardButton("✉️ إرسال رسالة لصاحب البوت", callback_data=CONTACT_ADMIN_CALLBACK)],
    ])


def is_type_question(text: str) -> bool:
    normalized = " ".join(text.strip().lower().split())
    return any(p in normalized for p in ("وش نوعك", "وش انت", "وش أنت", "ما نوعك", "ايش نوعك", "إيش نوعك"))


def fallback_reply(text: str) -> str:
    lowered = text.strip().lower()
    if is_type_question(text):
        return "انا بوت اقصد بوث 😝"
    if any(word in lowered for word in ("هلا", "مرحبا", "السلام", "hello")):
        return "يا هلا والله 🧡 نورت!"
    if "شكرا" in lowered or "مشكور" in lowered:
        return "العفو يا بعدي 🥹"
    if "كيفك" in lowered or "شلونك" in lowered:
        return "بخير دامك بخير 🔥"
    return "أبشر يا بعدي 🧡 اكتب طلبك وبحاول أفيدك."


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        context.user_data["ai_history"] = []
        await update.message.reply_text("نورت 👀", reply_markup=main_keyboard())


async def send_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text("حياك الله بالقناة 🧡\nاضغط الزر للدخول:", reply_markup=main_keyboard())


async def contact_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return
    await query.answer()
    context.user_data["awaiting_admin_message"] = True
    await query.message.reply_text("اكتب رسالتك الحين، وبوصلها لصاحب البوت ويرد عليك 🧡")


async def create_snapchat_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message or not query.from_user:
        return
    await query.answer()
    payload = f"{SNAPCHAT_PAYLOAD_PREFIX}:{query.from_user.id}:{uuid4().hex}"
    try:
        await query.message.reply_invoice(
            title="Snapchat 👻",
            description="Snapchat account — 250 ⭐️",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice("Snapchat 👻", SNAPCHAT_PRICE)],
            provider_token="",
            start_parameter="snapchat-sela-mon",
        )
    except Exception:
        logger.exception("Could not create Stars invoice")
        await query.message.reply_text("تعذر فتح الدفع الآن. تأكد أن البوت محدث ومفعل على Telegram Stars.")


async def precheckout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if not query:
        return
    valid = (query.currency == "XTR" and query.total_amount == SNAPCHAT_PRICE and
             query.invoice_payload.startswith(SNAPCHAT_PAYLOAD_PREFIX + ":"))
    if valid:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="بيانات الدفع غير صحيحة، حاول مرة أخرى.")


async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    payment = message.successful_payment if message else None
    if not message or not payment or not message.from_user:
        return
    if payment.currency != "XTR" or payment.total_amount != SNAPCHAT_PRICE:
        return
    record = {
        "product": "snapchat", "user_id": message.from_user.id,
        "username": message.from_user.username or "", "amount": payment.total_amount,
        "currency": payment.currency,
        "telegram_payment_charge_id": payment.telegram_payment_charge_id,
    }
    STORE["payments"].append(record)
    save_store()
    await message.reply_text(f"تم الدفع بنجاح ✅\n\nحساب Snapchat الخاص بك هو:\n{SNAPCHAT_USERNAME} 👻")
    try:
        await message.get_bot().send_message(
            chat_id=ADMIN_ID,
            text=f"💰 عملية شراء Snapchat\nالمستخدم: {message.from_user.id}\nالمبلغ: 250 نجمة\nCharge ID: {payment.telegram_payment_charge_id}",
        )
    except Exception:
        logger.exception("Could not notify admin")


async def deliver_to_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    message = update.message
    if not message or not message.from_user or message.from_user.id == ADMIN_ID:
        return False
    record = user_record(message.from_user.id, message.from_user)
    username = f"\n👤 username: @{message.from_user.username}" if message.from_user.username else ""
    header = await message.get_bot().send_message(
        chat_id=ADMIN_ID,
        text=f"📩 رسالة جديدة من {display_name(record)}\n🆔 ID: {message.from_user.id}{username}",
    )
    STORE["admin_messages"][str(header.message_id)] = message.from_user.id
    try:
        copied = await message.copy(chat_id=ADMIN_ID, reply_to_message_id=header.message_id)
        STORE["admin_messages"][str(copied.message_id)] = message.from_user.id
    except Exception:
        logger.exception("Could not copy user message")
    save_store()
    await message.reply_text("وصلت رسالتك لصاحب البوت ✅ إذا رد، يوصلك الرد هنا.")
    return True


async def admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    message = update.message
    if not message or not message.from_user or message.from_user.id != ADMIN_ID:
        return False
    replied = message.reply_to_message
    recipient_id = STORE["admin_messages"].get(str(replied.message_id)) if replied else None
    if not recipient_id:
        return False
    try:
        await message.copy(chat_id=int(recipient_id))
        await message.reply_text("تم إرسال الرد ✅")
    except Exception:
        await message.reply_text("ما قدرت أرسل الرد؛ يمكن المستخدم حظر البوت.")
    return True


async def rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user or update.message.from_user.id != ADMIN_ID:
        return
    if len(context.args) < 2:
        await update.message.reply_text("الاستخدام: /rename <رقم الشخص أو ID> <الاسم الجديد>")
        return
    identifier, new_name = context.args[0], " ".join(context.args[1:]).strip()
    record = next((item for item in STORE["users"].values() if str(item.get("person_number")) == identifier or str(item.get("user_id")) == identifier), None)
    if not record:
        await update.message.reply_text("ما لقيت هذا الشخص. استخدم /people لمعرفة الأرقام.")
        return
    record["name"] = new_name[:64]
    save_store()
    await update.message.reply_text(f"تم تغيير الاسم إلى: {record['name']} ✅")


async def people(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.from_user or update.message.from_user.id != ADMIN_ID:
        return
    records = sorted(STORE["users"].values(), key=lambda item: item["person_number"])
    if records:
        await update.message.reply_text("📋 الأشخاص:\n" + "\n".join(f"{display_name(x)} — ID: {x['user_id']}" for x in records))
    else:
        await update.message.reply_text("ما عندك متلقين مسجلين حاليًا.")


async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global client
    message = update.message
    if not message or not message.text or not message.from_user:
        return
    if await admin_reply(update, context):
        return
    if context.user_data.pop("awaiting_admin_message", False) and await deliver_to_admin(update, context):
        return
    await message.chat.send_action(ChatAction.TYPING)
    if any(word in message.text.lower() for word in ("رابط القناة", "لينك القناة", "رابط قناة", "channel link")):
        await send_channel_link(update, context)
        return
    if is_type_question(message.text):
        await message.reply_text("انا بوت اقصد بوث 😝")
        return
    reply = fallback_reply(message.text)
    if client:
        history = context.user_data.setdefault("ai_history", [])
        history.append({"role": "user", "content": message.text})
        history[:] = history[-MAX_HISTORY_MESSAGES:]
        try:
            result = await client.chat.completions.create(model=OPENAI_MODEL, temperature=0.7, max_tokens=600, messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history])
            reply = (result.choices[0].message.content or "").strip() or reply
            history.append({"role": "assistant", "content": reply})
            history[:] = history[-MAX_HISTORY_MESSAGES:]
        except Exception:
            logger.exception("AI request failed")
    await message.reply_text(reply)


async def forward_any_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("awaiting_admin_message"):
        context.user_data.pop("awaiting_admin_message", None)
        await deliver_to_admin(update, context)
    else:
        await admin_reply(update, context)


async def set_commands(application: Application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "بدء البوت"), BotCommand("channel", "رابط القناة"),
        BotCommand("rename", "تغيير اسم شخص - للمالك فقط"), BotCommand("people", "عرض الأشخاص - للمالك فقط"),
    ])


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("The TELEGRAM_BOT_TOKEN environment secret is not set")
    application = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("channel", send_channel_link))
    application.add_handler(CommandHandler("rename", rename))
    application.add_handler(CommandHandler("people", people))
    application.add_handler(CallbackQueryHandler(contact_admin, pattern=f"^{CONTACT_ADMIN_CALLBACK}$"))
    application.add_handler(CallbackQueryHandler(create_snapchat_invoice, pattern=f"^{SNAPCHAT_CALLBACK}$"))
    application.add_handler(PreCheckoutQueryHandler(precheckout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND & ~filters.TEXT, forward_any_message), group=0)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond), group=1)
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
