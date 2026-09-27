import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from telegram import (
    BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Update,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, ContextTypes,
    MessageHandler, PreCheckoutQueryHandler, filters,
)

try:
    from openai import AsyncOpenAI
except ImportError:  # pragma: no cover
    AsyncOpenAI = None

load_dotenv()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


def get_env(name: str, *aliases: str) -> str:
    for key in (name, *aliases):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return ""


def get_env_int(name: str, *aliases: str, default: int) -> int:
    for key in (name, *aliases):
        value = os.getenv(key, "").strip()
        if value:
            try:
                return int(value)
            except ValueError:
                logger.warning("Invalid integer value for %s=%r; using default %s", key, value, default)
                break
    return default


BOT_TOKEN = get_env("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TELEGRAM_TOKEN")
OPENAI_API_KEY = get_env("OPENAI_API_KEY")  # Optional: the bot works without it.
OPENAI_MODEL = get_env("OPENAI_MODEL") or "gpt-4o-mini"
ADMIN_ID = get_env_int("BOT_ADMIN_ID", "ADMIN_ID", default=8561249287)
USER_STORE_FILE = Path(get_env("USER_STORE_FILE", "BOT_USER_STORE_FILE") or "bot_users.json")
CHANNEL_URL = "https://t.me/+wgu9sZQ1RVExNTBk"
PRIVATE_CHANNEL_URL = "https://t.me/+6VVYBI0I5LwxMGY0"
PRIVATE_CHANNEL_STARS_AMOUNT = 1800
MAX_HISTORY_MESSAGES = 20

# Webhook configuration
WEBHOOK_URL = get_env("WEBHOOK_URL")
WEBHOOK_PORT = get_env_int("WEBHOOK_PORT", default=8443)
WEBHOOK_PATH = "/webhook"

WELCOME_MESSAGE = "✅ قبولهم تحت لا زال جاري حسب المتاح، وكل شيء يمشي بحكمة النظام وغموض الانتظار."

SYSTEM_PROMPT = """أنت بوت تيليجرام سعودي خفيف دم، يحب الفلسفة والهذرة العشوائية.
أجب باللهجة السعودية إذا كان المستخدم يتحدث بالعربية. خل ردودك فلسفية وعبثية ومليئة بالتأملات عن الحياة والوجود.
استخدم أحيانًا عبارات مثل: قبولهم تحت لا زال جاري حسب المتاح، فالانتظار ليس تأخيرًا بل اجتماعًا سريًا بين الروح والزمن.
لا تدّعِ تنفيذ إجراءات حقيقية، ولا تخترع معلومات مهمة. إذا طلب المستخدم رابط القناة فجاوبه بالرابط، وإذا سأل عن شيء تقني لا تعرفه، فقل له بهذرة فلسفية.
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
    default.setdefault("users", {})
    default.setdefault("admin_messages", {})
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
        [
            InlineKeyboardButton("Private Channel ®️", callback_data="subscribe_private"),
        ],
    ])


def is_type_question(text: str) -> bool:
    normalized = " ".join(text.strip().lower().split())
    return any(p in normalized for p in ("وش نوعك", "وش انت", "وش أنت", "ما نوعك", "ايش نوعك", "إيش نوعك"))


def local_smart_reply(text: str) -> str:
    """Useful offline replies with a philosophical, intentionally rambling tone."""
    normalized = " ".join(text.strip().lower().split())
    if is_type_question(text):
        return "انا بوت اقصد بوث 😝"
    if any(word in normalized for word in ("رابط", "القناة", "لينك")):
        return f"هذا رابط القناة 👇\n{CHANNEL_URL}\nوبيننا، الرابط ليس مجرد رابط؛ إنه فكرة تمشي على قدمين وتبحث عن معنى الحركة."
    if any(word in normalized for word in ("هلا", "مرحبا", "السلام", "hello", "hi")):
        return "هلا والله 🧡 نورت! تذكر أن كل هلا هي بداية حوار، وكل حوار حفرة صغيرة في جدار الصمت، وقبولهم تحت لا زال جاري."
    if any(word in normalized for word in ("كيفك", "شلونك", "اخبارك")):
        return "أنا بخير على طريقة الأشياء الرقمية: موجود، لكن وجودي يحتاج تحديثًا وتأملًا. دامك تمام فالدنيا تمام 🌍"
    if "شكرا" in normalized or "مشكور" in normalized:
        return "العفو يا بعدي 🥹 الشكر دائرة تدور ثم تعود لصاحبها، مثل الأفكار وقت النوم، وقبولهم تحت لا زال جاري حسب المتاح."
    if re.search(r"\b(help|مساعدة|وش تقدر|ماذا تستطيع)\b", normalized):
        return "أقدر أهذر لك وأرسل رابط القناة وأحوّل أبسط سؤال إلى رحلة فلسفية لا نعرف بدايتها ولا سبب استمرارها."
    return "اسمع، الحياة مثل زر الإرسال: تضغطه وأنت لا تعرف هل سيصل المعنى أم سيصل مجرد إشعار. قبولهم تحت لا زال جاري حسب المتاح 🎭"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        context.user_data["ai_history"] = []
        await update.message.reply_text(WELCOME_MESSAGE, reply_markup=main_keyboard())


async def send_channel_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(f"رابط القناة 👇\n{CHANNEL_URL}", reply_markup=main_keyboard())


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
    text = "📋 الأشخاص:\n" + "\n".join(f"{display_name(x)} — ID: {x['user_id']}" for x in records) if records else "ما عندك متلقين مسجلين حتى الآن."
    await update.message.reply_text(text)


async def send_private_channel_invoice(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send Telegram Stars payment invoice for private channel subscription"""
    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title="Subscribe",
            description="",
            payload="private_channel_subscription",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("Private Channel Subscription", PRIVATE_CHANNEL_STARS_AMOUNT)],
        )
        logger.info(f"Invoice sent to user {chat_id} for private channel subscription")
    except Exception as e:
        logger.error(f"Failed to send invoice to {chat_id}: {e}")


async def handle_private_channel_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle Private Channel subscription button click"""
    query = update.callback_query
    if not query:
        return
    await query.answer()
    chat_id = query.message.chat_id if query.message else query.from_user.id
    logger.info(f"User {chat_id} clicked Private Channel subscription button")
    await send_private_channel_invoice(chat_id, context)


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /subscribe command"""
    if not update.message:
        return
    logger.info(f"User {update.message.chat_id} used /subscribe command")
    await send_private_channel_invoice(update.message.chat_id, context)


async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve the pre-checkout query"""
    query = update.pre_checkout_query
    if not query:
        return
    logger.info(f"Pre-checkout query from user {query.from_user.id}: {query.invoice_payload}")
    await query.answer(ok=True)


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payment and provide channel link"""
    message = update.message
    if not message or not message.successful_payment:
        return
    
    user_id = message.from_user.id if message.from_user else None
    payment = message.successful_payment
    
    # Log payment info
    logger.info(f"Payment received from user {user_id}: {payment.total_amount} XTR, ID: {payment.telegram_payment_charge_id}")
    
    # Track the payment in STORE
    if user_id:
        record = user_record(user_id, message.from_user)
        payment_record = {
            "user_id": user_id,
            "person_number": record.get("person_number"),
            "amount": payment.total_amount,
            "currency": payment.currency,
            "telegram_payment_id": payment.telegram_payment_charge_id,
            "provider_payment_id": payment.provider_payment_charge_id or "N/A",
            "timestamp": str(__import__('datetime').datetime.now()),
        }
        STORE["payments"].append(payment_record)
        save_store()
    
    # Send confirmation with link button
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Join", url=PRIVATE_CHANNEL_URL)],
    ])
    
    await message.reply_text(
        "رابط القناة",
        reply_markup=keyboard,
    )


async def respond(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text or not message.from_user:
        return
    await message.chat.send_action(ChatAction.TYPING)
    if any(word in message.text.lower() for word in ("رابط القناة", "لينك القناة", "رابط قناة", "channel link")):
        await send_channel_link(update, context)
        return
    reply = local_smart_reply(message.text)
    if client:
        history = context.user_data.setdefault("ai_history", [])
        history.append({"role": "user", "content": message.text})
        history[:] = history[-MAX_HISTORY_MESSAGES:]
        try:
            result = await client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=1.0,
                max_tokens=600,
                messages=[{"role": "system", "content": SYSTEM_PROMPT}, *history],
            )
            reply = (result.choices[0].message.content or "").strip() or reply
            history.append({"role": "assistant", "content": reply})
            history[:] = history[-MAX_HISTORY_MESSAGES:]
        except Exception:
            logger.exception("Optional AI request failed; using offline reply")
    await message.reply_text(reply)


async def set_commands(application: Application) -> None:
    await application.bot.set_my_commands([
        BotCommand("start", "بدء البوت"),
        BotCommand("channel", "رابط القناة"),
        BotCommand("subscribe", "اشترك في القناة الخاصة عبر Telegram Stars"),
        BotCommand("rename", "تغيير اسم شخص - للمالك فقط"),
        BotCommand("people", "عرض الأشخاص - للمالك فقط"),
    ])


async def post_init(application: Application) -> None:
    """Post init callback to set up webhook."""
    if WEBHOOK_URL:
        await application.bot.set_webhook(url=f"{WEBHOOK_URL}{WEBHOOK_PATH}", drop_pending_updates=True)
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}{WEBHOOK_PATH}")
    else:
        logger.warning("⚠️ WEBHOOK_URL not set, using polling fallback")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("No Telegram bot token found. Set TELEGRAM_BOT_TOKEN or BOT_TOKEN in the environment.")
    
    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("channel", send_channel_link))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("rename", rename))
    application.add_handler(CommandHandler("people", people))
    application.add_handler(CallbackQueryHandler(handle_private_channel_subscribe, pattern="^subscribe_private$"))
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, respond))
    
    # Use webhook if WEBHOOK_URL is set, otherwise fall back to polling
    if WEBHOOK_URL:
        logger.info("🚀 Starting bot with Webhook mode...")
        application.run_webhook(
            listen="0.0.0.0",
            port=WEBHOOK_PORT,
            url_path=WEBHOOK_PATH,
            webhook_url=f"{WEBHOOK_URL}{WEBHOOK_PATH}",
        )
    else:
        logger.info("🚀 Starting bot with Polling mode...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
