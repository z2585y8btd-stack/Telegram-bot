import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔥 Join Private Channel 🔥",
                url="https://t.me/+LIVzUK7_TxphNGZk"
            )
        ]
    ])

    await update.message.reply_text(
        "⭐ Welcome to SullfitBot ⭐",
        reply_markup=keyboard
    )

app = Application.builder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))

print("Bot is running...")
app.run_polling()
