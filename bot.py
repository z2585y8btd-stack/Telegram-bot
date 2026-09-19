import json
import os
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_ID = 8561249287
MUSIC_FILE = Path(os.environ.get("MUSIC_FILE", "music_file_id.txt"))
INBOX_FILE = Path(os.environ.get("ANONYMOUS_INBOX_FILE", "anonymous_inbox.json"))
ALIASES_FILE = Path(os.environ.get("ANONYMOUS_ALIASES_FILE", "anonymous_aliases.json"))
PRIVATE_CHANNEL_BUTTON = "🔥 Private Channel 🔥"


def load_inbox() -> dict[str, int]:
    if not INBOX_FILE.exists():
        return {}
    try:
        data = json.loads(INBOX_FILE.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    inbox = {}
    for key, value in data.items():
        try:
            inbox[str(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return inbox


def save_inbox(inbox: dict[str, int]) -> None:
    temp_file = INBOX_FILE.with_suffix(f"{INBOX_FILE.suffix}.tmp")
    temp_file.write_text(json.dumps(inbox), encoding="utf-8")
    temp_file.replace(INBOX_FILE)


def load_aliases() -> dict[str, dict[str, str]]:
    if not ALIASES_FILE.exists():
        return {}
    try:
        data = json.loads(ALIASES_FILE.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    aliases = {}
    for user_id, record in data.items():
        if isinstance(record, str):
            aliases[str(user_id)] = {"alias": record, "name": record}
        elif isinstance(record, dict) and record.get("alias"):
            aliases[str(user_id)] = {
                "alias": str(record["alias"]),
                "name": str(record.get("name") or record["alias"]),
            }
    return aliases


def save_aliases(aliases: dict[str, dict[str, str]]) -> None:
    temp_file = ALIASES_FILE.with_suffix(f"{ALIASES_FILE.suffix}.tmp")
    temp_file.write_text(json.dumps(aliases, ensure_ascii=False), encoding="utf-8")
    temp_file.replace(ALIASES_FILE)


inbox = load_inbox()
aliases = load_aliases()


def get_sender_label(user_id: int) -> str:
    key = str(user_id)
    record = aliases.get(key)
    if record is None:
        record = {"alias": f"User {len(aliases) + 1}", "name": ""}
        aliases[key] = record
        save_aliases(aliases)
    return record["name"] or record["alias"]


def private_channel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(
                PRIVATE_CHANNEL_BUTTON,
                url="https://t.me/+LIVzUK7_TxphNGZk",
            )
        ]]
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "",
        reply_markup=private_channel_markup(),
    )


async def set_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return

    message = update.message
    replied_to = message.reply_to_message
    audio = replied_to.audio if replied_to else None
    if not audio or (
        audio.mime_type
        and audio.mime_type != "audio/mpeg"
        and not (audio.file_name or "").lower().endswith(".mp3")
    ):
        await message.reply_text("Reply to an MP3 audio file with /setmusic.")
        return

    MUSIC_FILE.write_text(audio.file_id, encoding="utf-8")
    await message.reply_text("Music updated successfully.")


async def rename_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != OWNER_ID:
        return
    if len(context.args) < 3 or context.args[0].lower() != "user":
        await update.message.reply_text("Usage: /rename User <number> <name>")
        return

    alias = f"User {context.args[1]}"
    new_name = " ".join(context.args[2:]).strip()
    if not new_name:
        await update.message.reply_text("Usage: /rename User <number> <name>")
        return

    for record in aliases.values():
        if record["alias"].casefold() == alias.casefold():
            record["name"] = new_name
            save_aliases(aliases)
            await update.message.reply_text(f"{alias} renamed to {new_name}.")
            return
    await update.message.reply_text(f"No sender found for {alias}.")


async def play_music(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not MUSIC_FILE.exists():
        await update.message.reply_text("No music has been set yet.")
        return

    file_id = MUSIC_FILE.read_text(encoding="utf-8").strip()
    if not file_id:
        await update.message.reply_text("No music has been set yet.")
        return
    await update.message.reply_audio(audio=file_id)


def is_media_message(message) -> bool:
    return bool(
        message.photo
        or message.video
        or message.document
        or message.audio
        or message.voice
        or message.video_note
        or message.animation
        or message.sticker
    )


def get_message_text(message) -> str:
    return message.text if message.text is not None else (message.caption or "")


async def forward_user_message_to_owner(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    message = update.message
    user = update.effective_user
    if not message or user is None or (message.text and message.text.startswith("/")):
        return

    sender_label = get_sender_label(user.id)
    header = f"🧑‍💻 {sender_label}"
    if message.text:
        forwarded_message = await context.bot.send_message(
            chat_id=OWNER_ID,
            text=f"{header}\n\n{message.text}",
        )
    elif is_media_message(message):
        content = get_message_text(message)
        caption = header if not content else f"{header}\n\n{content}"
        forwarded_message = await context.bot.copy_message(
            chat_id=OWNER_ID,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
            caption=caption[:1024],
        )
    else:
        return

    inbox[str(forwarded_message.message_id)] = user.id
    save_inbox(inbox)


async def handle_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.reply_to_message:
        return

    replied_message = message.reply_to_message
    if replied_message.from_user is None or replied_message.from_user.id != context.bot.id:
        return

    recipient_id = inbox.get(str(replied_message.message_id))
    if recipient_id is None:
        return

    if message.text:
        await context.bot.send_message(chat_id=recipient_id, text=message.text)
    elif is_media_message(message):
        await context.bot.copy_message(
            chat_id=recipient_id,
            from_chat_id=message.chat_id,
            message_id=message.message_id,
        )


async def handle_incoming_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or update.effective_user is None:
        return
    if update.effective_user.id == OWNER_ID:
        await handle_owner_reply(update, context)
        return
    await forward_user_message_to_owner(update, context)


app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setmusic", set_music))
app.add_handler(CommandHandler("music", play_music))
app.add_handler(CommandHandler("rename", rename_user))
app.add_handler(MessageHandler(filters.ALL, handle_incoming_message))

print("Bot is running...")
app.run_polling()
