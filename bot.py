import os
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
OWNER_ID = int(os.environ["TELEGRAM_OWNER_ID"])
MUSIC_FILE = Path(os.environ.get("MUSIC_FILE", "music_file_id.txt"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔥 Private Channel 🔥",
                url="https://t.me/+LIVzUK7_TxphNGZk"
            )
        ],
        [
            InlineKeyboardButton(
                "📩 Send Anonymous Message",
                url="https://t.me/boxxxsabot"
            )
        ],
        [InlineKeyboardButton("🎵 Play Music 🎵", callback_data="play_music")],
    ])

    await update.message.reply_text(
        "⭐ Welcome to SullfitBot ⭐",
        reply_markup=keyboard
    )


async def set_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return

    message = update.message
    replied_to = message.reply_to_message
    audio = replied_to.audio if replied_to else None

    if not audio or (
        audio.mime_type and audio.mime_type != "audio/mpeg"
        and not (audio.file_name or "").lower().endswith(".mp3")
    ):
        await message.reply_text("Reply to an MP3 audio file with /setmusic.")
        return

    MUSIC_FILE.write_text(audio.file_id, encoding="utf-8")
    await message.reply_text("Music updated successfully.")


async def play_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not MUSIC_FILE.exists():
        await query.message.reply_text("No music has been set yet.")
        return

    file_id = MUSIC_FILE.read_text(encoding="utf-8").strip()
    if not file_id:
        await query.message.reply_text("No music has been set yet.")
        return

    await query.message.reply_audio(audio=file_id)


app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setmusic", set_music))
app.add_handler(CallbackQueryHandler(play_music, pattern="^play_music$"))

print("Bot is running...")
app.run_polling()
