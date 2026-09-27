import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

TEST_DIR = tempfile.mkdtemp(prefix="telegram_bot_tests_")
os.environ["BOT_USER_STORE_FILE"] = os.path.join(TEST_DIR, "store.json")

import bot


class PaymentFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_invoice_requires_provider_token(self) -> None:
        original_token = bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN
        original_chat_id = bot.PRIVATE_CHANNEL_CHAT_ID
        bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN = ""
        bot.PRIVATE_CHANNEL_CHAT_ID = "@private_channel"
        mock_bot = SimpleNamespace(send_message=AsyncMock(), send_invoice=AsyncMock())
        context = SimpleNamespace(bot=mock_bot)
        try:
            await bot.send_private_channel_invoice(123, context)
            mock_bot.send_message.assert_awaited()
            mock_bot.send_invoice.assert_not_called()
        finally:
            bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN = original_token
            bot.PRIVATE_CHANNEL_CHAT_ID = original_chat_id

    async def test_invoice_requires_private_channel_chat_id(self) -> None:
        original_token = bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN
        original_chat_id = bot.PRIVATE_CHANNEL_CHAT_ID
        bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN = "provider_token"
        bot.PRIVATE_CHANNEL_CHAT_ID = ""
        mock_bot = SimpleNamespace(send_message=AsyncMock(), send_invoice=AsyncMock())
        context = SimpleNamespace(bot=mock_bot)
        try:
            await bot.send_private_channel_invoice(123, context)
            mock_bot.send_message.assert_awaited()
            mock_bot.send_invoice.assert_not_called()
        finally:
            bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN = original_token
            bot.PRIVATE_CHANNEL_CHAT_ID = original_chat_id

    async def test_invoice_uses_provider_token_and_xtr(self) -> None:
        original_token = bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN
        original_chat_id = bot.PRIVATE_CHANNEL_CHAT_ID
        bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN = "provider_token"
        bot.PRIVATE_CHANNEL_CHAT_ID = "@private_channel"
        mock_bot = SimpleNamespace(send_message=AsyncMock(), send_invoice=AsyncMock())
        context = SimpleNamespace(bot=mock_bot)
        try:
            await bot.send_private_channel_invoice(123, context)
            mock_bot.send_invoice.assert_awaited_once()
            kwargs = mock_bot.send_invoice.await_args.kwargs
            self.assertEqual(kwargs["provider_token"], "provider_token")
            self.assertEqual(kwargs["currency"], "XTR")
            self.assertEqual(kwargs["description"], "ادفع عبر Telegram Stars للحصول على رابط الانضمام للقناة الخاصة.")
        finally:
            bot.TELEGRAM_PAYMENT_PROVIDER_TOKEN = original_token
            bot.PRIVATE_CHANNEL_CHAT_ID = original_chat_id

    def test_format_xtr_amount(self) -> None:
        self.assertEqual(bot.format_payment_amount(1800, "XTR"), "1800 Stars")
        self.assertEqual(bot.format_payment_amount(0, "XTR"), "0 Stars")
        self.assertEqual(bot.format_payment_amount(1, "XTR"), "1 Stars")
        self.assertEqual(bot.format_payment_amount(250, "USD"), "2.50 USD")
        self.assertEqual(bot.format_payment_amount(500, "jpy"), "500 JPY")


if __name__ == "__main__":
    unittest.main()
