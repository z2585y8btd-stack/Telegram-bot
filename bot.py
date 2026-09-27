import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from telegram import Chat, Update, LabeledPrice
from telegram.ext import (
    Application, ChatMemberHandler, CommandHandler, ContextTypes,
    PreCheckoutQueryHandler, MessageHandler, filters,
)

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
ADMIN_ID = get_env_int("BOT_ADMIN_ID", "ADMIN_ID", default=8561249287)
USER_STORE_FILE = Path(get_env("USER_STORE_FILE", "BOT_USER_STORE_FILE") or "bot_users.json")

# Optional: if the bot is an admin in more than one channel, this bot setting
# picks which one to use. Not required — if left empty and the bot is only
# an admin (with invite-link permissions) in a single channel, that channel
# is auto-detected and used at runtime.
TARGET_CHANNEL = get_env("TARGET_CHANNEL", "TARGET_CHANNEL_ID", "PRIVATE_CHANNEL_ID")

PRIVATE_CHANNEL_STARS_AMOUNT = 1800

# Webhook configuration
WEBHOOK_URL = get_env("WEBHOOK_URL")
WEBHOOK_PORT = get_env_int("WEBHOOK_PORT", default=8443)
WEBHOOK_PATH = "/webhook"

ACCEPT_MESSAGE = "Accept✅"


def load_store() -> dict[str, Any]:
    default = {
        "next_person": 1,
        "users": {},
        "payments": [],
        "invite_links": {},
        "admin_channels": {},
    }
    try:
        if USER_STORE_FILE.exists():
            default.update(json.loads(USER_STORE_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not load user store")
    default.setdefault("users", {})
    default.setdefault("payments", [])
    default.setdefault("invite_links", {})
    default.setdefault("admin_channels", {})
    return default


STORE = load_store()


def save_store() -> None:
    temporary = USER_STORE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(STORE, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(USER_STORE_FILE)


def user_record(user_id: int, user: Any) -> dict[str, Any]:
    key = str(user_id)
    record = STORE["users"].get(key)
    if not record:
        number = int(STORE["next_person"])
        STORE["next_person"] = number + 1
        record = {"person_number": number, "user_id": user_id}
        STORE["users"][key] = record
    record["username"] = user.username or ""
    record["first_name"] = user.first_name or ""
    save_store()
    return record


def _remember_admin_channel(chat: Chat, can_invite_users: bool) -> None:
    key = str(chat.id)
    if can_invite_users:
        STORE["admin_channels"][key] = {
            "id": chat.id,
            "title": chat.title or "",
            "username": chat.username or "",
        }
    else:
        STORE["admin_channels"].pop(key, None)
    save_store()


def _forget_admin_channel(chat: Chat) -> None:
    STORE["admin_channels"].pop(str(chat.id), None)
    save_store()


async def get_target_channel_id(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Automatically determine the channel to use.

    Resolution order:
    1. If TARGET_CHANNEL is set (an explicit bot setting), use it — this lets
       the operator pick a channel when the bot administers more than one.
    2. If exactly one channel has been detected where the bot is an admin with
       invite-link permissions, use that channel automatically.
    3. Otherwise, the channel cannot be determined automatically.
    """
    if TARGET_CHANNEL:
        value = TARGET_CHANNEL
        try:
            return int(value)
        except ValueError:
            try:
                chat = await context.bot.get_chat(value)
                return chat.id
            except Exception:
                logger.exception(f"Configured TARGET_CHANNEL {value!r} could not be resolved")
                return None

    channels = STORE.get("admin_channels", {})
    if len(channels) == 1:
        return next(iter(channels.values()))["id"]
    if len(channels) > 1:
        logger.error(
            "Bot is admin with invite permissions in multiple channels %s; "
            "set TARGET_CHANNEL to pick one.",
            list(channels.keys()),
        )
        return None
    return None


async def handle_my_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Track channels where the bot is added/promoted/removed as admin.

    This lets the bot automatically detect the channel it should manage,
    without any manual chat-id configuration.
    """
    my_update = update.my_chat_member
    if not my_update or my_update.chat.type not in (Chat.CHANNEL,):
        return

    new_member = my_update.new_chat_member
    status = new_member.status
    if status == "administrator":
        can_invite = bool(getattr(new_member, "can_invite_users", False))
        _remember_admin_channel(my_update.chat, can_invite)
        if can_invite:
            logger.info(f"Detected channel '{my_update.chat.title}' ({my_update.chat.id}) as admin with invite permissions")
        else:
            logger.warning(f"Bot is admin in '{my_update.chat.title}' ({my_update.chat.id}) but lacks invite-link permission")
    else:
        _forget_admin_channel(my_update.chat)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Default /start handler: send Accept✅ message, then the Stars payment invoice."""
    if not update.message:
        return
    chat_id = update.message.chat_id
    await update.message.reply_text(ACCEPT_MESSAGE)
    await send_private_channel_invoice(chat_id, context)


async def send_private_channel_invoice(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the Telegram Stars payment invoice (1800 ⭐) as the payment button."""
    try:
        await context.bot.send_invoice(
            chat_id=chat_id,
            title=f"{PRIVATE_CHANNEL_STARS_AMOUNT} ⭐",
            description=f"{PRIVATE_CHANNEL_STARS_AMOUNT} ⭐",
            payload="private_channel_subscription",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(f"{PRIVATE_CHANNEL_STARS_AMOUNT} ⭐", PRIVATE_CHANNEL_STARS_AMOUNT)],
        )
        logger.info(f"Invoice sent to user {chat_id} for private channel subscription")
    except Exception as e:
        logger.error(f"Failed to send invoice to {chat_id}: {e}")


async def handle_pre_checkout_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve the pre-checkout query."""
    query = update.pre_checkout_query
    if not query:
        return
    logger.info(f"Pre-checkout query from user {query.from_user.id}: {query.invoice_payload}")
    await query.answer(ok=True)


async def create_unique_invite_link(context: ContextTypes.DEFAULT_TYPE, channel_id: int, user_id: int) -> Optional[str]:
    """Create a single-use invite link tied to one user."""
    try:
        invite = await context.bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1,
            name=f"user-{user_id}",
        )
        STORE["invite_links"][invite.invite_link] = {
            "user_id": user_id,
            "channel_id": channel_id,
            "revoked": False,
        }
        save_store()
        return invite.invite_link
    except Exception:
        logger.exception(f"Failed to create invite link for user {user_id}")
        return None


async def handle_successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle successful payment: generate a unique invite link and send it to the payer only."""
    message = update.message
    if not message or not message.successful_payment:
        return

    user_id = message.from_user.id if message.from_user else None
    payment = message.successful_payment

    logger.info(f"Payment received from user {user_id}: {payment.total_amount} XTR, ID: {payment.telegram_payment_charge_id}")

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

    channel_id = await get_target_channel_id(context)
    if not channel_id:
        logger.error("Could not automatically determine the target channel; payment flow stopped")
        await message.reply_text(
            "Payment received, but the invite link could not be created. Please contact support."
        )
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "⚠️ Could not determine the target channel automatically.\n"
                        "Make sure the bot is an administrator with invite-link "
                        "permissions in exactly one channel, or set TARGET_CHANNEL.\n"
                        f"Payment from user {user_id} was received but no invite link was issued."
                    ),
                )
            except Exception:
                logger.exception("Failed to notify admin about missing target channel")
        return

    invite_link = await create_unique_invite_link(context, channel_id, user_id) if user_id else None

    if invite_link:
        await message.reply_text(invite_link)
    else:
        await message.reply_text("Payment received, but the invite link could not be created. Please contact support.")


async def handle_chat_member_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """When a user joins the channel via an invite link, revoke that link automatically."""
    chat_member_update = update.chat_member
    if not chat_member_update:
        return

    new_status = chat_member_update.new_chat_member.status
    old_status = chat_member_update.old_chat_member.status
    invite_link_obj = chat_member_update.invite_link

    if not invite_link_obj:
        return

    joined = new_status == "member" and old_status in ("left", "kicked", "restricted")
    if not joined:
        return

    invite_link = invite_link_obj.invite_link
    link_info = STORE["invite_links"].get(invite_link)
    if not link_info or link_info.get("revoked"):
        return

    channel_id = link_info.get("channel_id") or chat_member_update.chat.id
    try:
        await context.bot.revoke_chat_invite_link(chat_id=channel_id, invite_link=invite_link)
        link_info["revoked"] = True
        save_store()
        logger.info(f"Revoked invite link for user {link_info.get('user_id')} after they joined")
    except Exception:
        logger.exception(f"Failed to revoke invite link {invite_link}")


async def ignore_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ignore any other text messages; the flow only uses /start."""
    return


async def post_init(application: Application) -> None:
    """Post init callback to set up webhook."""
    await application.bot.set_my_commands([])
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
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
    application.add_handler(ChatMemberHandler(handle_my_chat_member_update, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(handle_chat_member_update, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ignore_text))

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
