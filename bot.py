import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from telegram import Chat, Update, LabeledPrice
from telegram.ext import (
    Application, ChatMemberHandler, CommandHandler, ContextTypes,
    PreCheckoutQueryHandler, MessageHandler, TypeHandler, filters,
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
        "target_channel": None,
    }
    try:
        if USER_STORE_FILE.exists():
            default.update(json.loads(USER_STORE_FILE.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not load user store")
    default.setdefault("users", {})
    default.setdefault("payments", [])
    default.setdefault("invite_links", {})
    default.setdefault("target_channel", None)
    
    # Log loaded target channel on startup
    target = default.get("target_channel")
    if target:
        logger.info(f"✅ Loaded saved target channel: {target.get('title')} (ID: {target.get('id')})")
    else:
        logger.warning("⚠️ No target channel configured in store")
    
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


async def get_target_channel_id(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
    """Get the saved target channel ID for payment invites."""
    channel_info = STORE.get("target_channel")
    if not channel_info:
        return None
    return channel_info.get("id")


async def setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Set the current channel as the target payment channel (admin-only).
    
    Usage: Send /setchannel inside the channel where the bot is an admin.
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    user_id = user.id if user else "anonymous"

    logger.info(f"[/setchannel] Received from user {user_id} in chat {chat.id if chat else 'unknown'}")

    if not message or not chat:
        logger.warning("[/setchannel] No message object")
        return

    bot_member = None

    # Only the bot owner can use this command
    if user:
        if user.id != ADMIN_ID:
            logger.warning(f"[/setchannel] Unauthorized user {user.id} tried to use /setchannel")
            await message.reply_text("❌ Only the bot owner can use this command.")
            return
    else:
        if not (chat.type == Chat.CHANNEL or str(chat.id).startswith("-100")):
            logger.warning(f"[/setchannel] Anonymous update from unsupported chat type {chat.type}")
            await message.reply_text("❌ Only the bot owner can use this command.")
            return
        try:
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status != "administrator":
                logger.warning(f"[/setchannel] Anonymous authorization denied: bot is not admin in {chat.id}")
                await message.reply_text("❌ Only the bot owner can use this command.")
                return
            logger.warning(f"[/setchannel] Anonymous channel authorization used in chat {chat.id}")
        except Exception as e:
            logger.exception(f"[/setchannel] Failed anonymous authorization check in {chat.id}")
            await message.reply_text(f"❌ Error verifying bot permissions: {e}")
            return

    logger.info(f"[/setchannel] Chat type: {chat.type}, Chat ID: {chat.id}, Chat title: {chat.title}")
    
    # Command must be used in a channel (group or supergroup)
    if chat.type not in (Chat.CHANNEL, Chat.SUPERGROUP, Chat.GROUP):
        logger.error(f"[/setchannel] Invalid chat type: {chat.type}. Supported: CHANNEL, SUPERGROUP, GROUP")
        error_msg = (
            "❌ This command must be used inside a channel or group.\n\n"
            f"Current chat type: {chat.type}\n"
            "Supported: Channel (CHANNEL), Supergroup (SUPERGROUP), or Group (GROUP)"
        )
        await message.reply_text(error_msg)
        return

    # Verify the bot is an admin in this chat
    try:
        if bot_member is None:
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
        logger.info(f"[/setchannel] Bot status in {chat.id}: {bot_member.status}")

        if bot_member.status != "administrator":
            logger.error(f"[/setchannel] Bot is not an administrator in {chat.id}")
            await message.reply_text("❌ The bot must be an administrator in this channel.")
            return

        # Check if bot has permission to manage invite links
        can_invite = getattr(bot_member, "can_invite_users", False)
        logger.info(f"[/setchannel] Bot can_invite_users permission: {can_invite}")

        if not can_invite:
            logger.error(f"[/setchannel] Bot lacks can_invite_users permission in {chat.id}")
            await message.reply_text(
                "❌ The bot must have permission to manage invite links in this channel."
            )
            return
    except Exception as e:
        logger.exception(f"[/setchannel] Failed to verify bot admin status in {chat.id}")
        await message.reply_text(f"❌ Error verifying bot permissions: {e}")
        return

    # Save this channel as the target
    channel_title = chat.title or chat.name or f"Channel {chat.id}"
    STORE["target_channel"] = {
        "id": chat.id,
        "title": channel_title,
        "username": chat.username or "",
    }
    save_store()
    
    logger.info(f"[/setchannel] ✅ Channel saved: {channel_title} (ID: {chat.id})")
    
    # Confirm to the owner
    channel_info = STORE["target_channel"]
    title = channel_info["title"]
    channel_id = channel_info["id"]
    username = channel_info.get("username", "")
    
    confirmation = f"✅ Channel registered successfully\nChannel: {title}\nChannel ID: {channel_id}"
    if username:
        confirmation += f"\nUsername: @{username}"

    await message.reply_text(confirmation)


async def channelinfo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show information about the saved target channel and bot permissions.
    
    Usage: Send /channelinfo (works in any chat)
    """
    message = update.effective_message
    chat = update.effective_chat
    user = update.effective_user
    user_id = user.id if user else "anonymous"

    logger.info(f"[/channelinfo] Received from user {user_id}")

    if not message:
        return

    # Only the bot owner can use this command
    if user:
        if user.id != ADMIN_ID:
            logger.warning(f"[/channelinfo] Unauthorized user {user.id}")
            await message.reply_text("❌ Only the bot owner can use this command.")
            return
    else:
        if not chat or not (chat.type == Chat.CHANNEL or str(chat.id).startswith("-100")):
            logger.warning("[/channelinfo] Anonymous update from unsupported chat")
            await message.reply_text("❌ Only the bot owner can use this command.")
            return
        try:
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            if bot_member.status != "administrator":
                logger.warning(f"[/channelinfo] Anonymous authorization denied in {chat.id}")
                await message.reply_text("❌ Only the bot owner can use this command.")
                return
            logger.warning(f"[/channelinfo] Anonymous channel authorization used in chat {chat.id}")
        except Exception as e:
            logger.exception(f"[/channelinfo] Failed anonymous authorization check in {chat.id}")
            await message.reply_text(f"❌ Error verifying bot permissions: {e}")
            return

    target = STORE.get("target_channel")
    if not target:
        logger.info("[/channelinfo] No target channel configured")
        await message.reply_text("ℹ️ No target channel configured yet.\n\nUse /setchannel in your target channel to register it.")
        return

    channel_id = target.get("id")
    channel_title = target.get("title", "Unknown")
    channel_username = target.get("username", "")
    
    logger.info(f"[/channelinfo] Checking bot permissions in channel {channel_id}")
    
    # Try to verify current bot permissions
    try:
        bot_member = await context.bot.get_chat_member(channel_id, context.bot.id)
        status = bot_member.status
        can_invite = getattr(bot_member, "can_invite_users", False)
        
        logger.info(f"[/channelinfo] Bot status: {status}, can_invite: {can_invite}")
        
        status_emoji = "✅" if status == "administrator" else "⚠️"
        invite_emoji = "✅" if can_invite else "❌"
        
        info = (
            f"📋 Saved Target Channel\n\n"
            f"Channel: {channel_title}\n"
            f"Channel ID: {channel_id}\n"
        )
        if channel_username:
            info += f"Username: @{channel_username}\n"
        
        info += (
            f"\n🤖 Bot Permissions\n"
            f"{status_emoji} Admin Status: {status}\n"
            f"{invite_emoji} Invite Links: {'Allowed' if can_invite else 'Denied'}"
        )
        
        await message.reply_text(info)
    except Exception as e:
        logger.exception(f"[/channelinfo] Error checking permissions in {channel_id}")

        info = (
            f"📋 Saved Target Channel\n\n"
            f"Channel: {channel_title}\n"
            f"Channel ID: {channel_id}\n"
        )
        if channel_username:
            info += f"Username: @{channel_username}\n"

        info += f"\n⚠️ Could not verify current bot permissions (Error: {e})"

        await message.reply_text(info)


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
        logger.error("No target channel configured; payment flow stopped")
        await message.reply_text(
            "Payment received, but the invite link could not be created. Please contact support."
        )
        if ADMIN_ID:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=(
                        "⚠️ No target payment channel has been configured.\n"
                        "Use /setchannel in the channel where the bot should send invite links.\n"
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


def extract_command_text(update: Update) -> Optional[str]:
    message = update.effective_message
    if not message:
        return None
    text = message.text or message.caption or ""
    text = text.strip()
    if not text.startswith("/"):
        return None
    return text.split()[0]


async def log_incoming_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        update_type = "message"
    elif update.channel_post:
        update_type = "channel_post"
    elif update.edited_channel_post:
        update_type = "edited_channel_post"
    elif update.my_chat_member:
        update_type = "my_chat_member"
    else:
        update_type = "other"

    logger.info("[UPDATE RECEIVED] type=%s update_id=%s", update_type, update.update_id)

    command = extract_command_text(update)
    if not command:
        return

    logger.info("[COMMAND RECEIVED] %s from update_id=%s", command, update.update_id)
    chat = update.effective_chat
    if update.channel_post and chat and (chat.type == Chat.CHANNEL or str(chat.id).startswith("-100")):
        logger.info("[CHANNEL COMMAND RECEIVED] %s in chat %s", command, chat.id)


def log_registered_handlers(application: Application) -> None:
    logger.info("📋 Registered handlers:")
    for group in sorted(application.handlers):
        for handler in application.handlers[group]:
            if isinstance(handler, CommandHandler):
                commands = ", ".join(f"/{command}" for command in handler.commands)
                logger.info("  - CommandHandler: %s", commands)
            elif isinstance(handler, MessageHandler):
                if handler.callback == setchannel:
                    logger.info("  - MessageHandler (channel post): /setchannel [%s]", handler.filters)
                elif handler.callback == channelinfo:
                    logger.info("  - MessageHandler (channel post): /channelinfo [%s]", handler.filters)
                else:
                    logger.info("  - MessageHandler: %s", handler.filters)
            elif isinstance(handler, ChatMemberHandler):
                chat_member_type = "my_chat_member" if handler.chat_member_types == ChatMemberHandler.MY_CHAT_MEMBER else "chat_member"
                logger.info("  - ChatMemberHandler: %s", chat_member_type)
            elif isinstance(handler, TypeHandler):
                type_name = getattr(handler.type, "__name__", str(handler.type))
                logger.info("  - TypeHandler: %s", type_name)
            else:
                logger.info("  - %s", handler.__class__.__name__)


async def post_init(application: Application) -> None:
    """Post init callback to set up webhook."""
    logger.info("🚀 Bot starting up...")
    log_registered_handlers(application)
    await application.bot.set_my_commands([])
    if WEBHOOK_URL:
        await application.bot.set_webhook(
            url=f"{WEBHOOK_URL}{WEBHOOK_PATH}",
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES,
        )
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"✅ Webhook set to {WEBHOOK_URL}{WEBHOOK_PATH}")
        logger.info("📡 Webhook allowed_updates: %s", webhook_info.allowed_updates)
    else:
        logger.warning("⚠️ WEBHOOK_URL not set, using polling fallback")


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("No Telegram bot token found. Set TELEGRAM_BOT_TOKEN or BOT_TOKEN in the environment.")

    application = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    application.add_handler(TypeHandler(Update, log_incoming_update), group=-1)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setchannel", setchannel))
    application.add_handler(CommandHandler("channelinfo", channelinfo))
    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POSTS & filters.TEXT & filters.Regex(r"(?i)^\s*/setchannel(@\w+)?\s*$"),
            setchannel,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POSTS & filters.TEXT & filters.Regex(r"(?i)^\s*/channelinfo(@\w+)?\s*$"),
            channelinfo,
        )
    )
    application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout_query))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment))
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
            allowed_updates=Update.ALL_TYPES,
        )
    else:
        logger.info("🚀 Starting bot with Polling mode...")
        logger.info("Allowed updates for polling: %s", Update.ALL_TYPES)
        application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
