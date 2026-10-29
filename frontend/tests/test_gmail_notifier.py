import unittest
from unittest.mock import patch

from backend.notifications import gmail_notifier


class GmailNotifierTests(unittest.TestCase):
    def test_add_email_contains_average_take_profits_and_stop(self):
        captured = {}

        def capture_message(sender, app_password, recipient, subject, body):
            captured.update(subject=subject, body=body)

        result = {
            "mode": "PAPER",
            "direction": "LONG",
            "entry_price": 80_000.0,
            "added_entry_price": 79_500.0,
            "added_size_btc": 0.00628931,
            "average_entry_price": 79_811.96,
            "stop_loss": 79_061.96,
            "take_profit_1": 80_311.96,
            "take_profit_2": 81_011.96,
            "position_size_percent": 100.0,
            "entry_stage": 3,
        }

        with patch.object(
            gmail_notifier,
            "load_gmail_config",
            return_value=("sender@example.com", "password", "recipient@example.com"),
        ), patch.object(gmail_notifier, "_send_message", side_effect=capture_message):
            sent, recipient = gmail_notifier.send_trade_event_email("ADD", result)

        self.assertTrue(sent)
        self.assertEqual(recipient, "recipient@example.com")
        self.assertIn("추가 진입 · 총 100%", captured["subject"])
        self.assertIn("현재 평균단가: 79,811.96 USDT", captured["body"])
        self.assertIn("현재 손절가: 79,061.96 USDT", captured["body"])
        self.assertIn("현재 1차 익절가: 80,311.96 USDT", captured["body"])
        self.assertIn("현재 2차 익절가: 81,011.96 USDT", captured["body"])


if __name__ == "__main__":
    unittest.main()
