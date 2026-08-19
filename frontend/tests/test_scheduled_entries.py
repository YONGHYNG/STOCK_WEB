import unittest
from datetime import datetime
from types import SimpleNamespace

from backend.scheduled_entries import (
    KST,
    active_scheduled_session,
    build_forced_entry_result,
    choose_forced_direction,
)


class ScheduledEntryTests(unittest.TestCase):
    def test_windows_and_overnight_session_date(self):
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 8, 50, tzinfo=KST)), ("2026-08-19", "MORNING"))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 16, 30, tzinfo=KST)), ("2026-08-19", "EUROPE"))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 20, 0, 10, tzinfo=KST)), ("2026-08-19", "US"))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 12, 0, tzinfo=KST)))

    def test_hold_uses_indicator_bias(self):
        result = {
            "direction": "HOLD", "long_probability": 50, "short_probability": 50,
            "diagnostics": {"metrics": {"close": 101, "ema20": 100, "ema50": 99, "vwap": 100, "ema20_slope": 1}},
            "timeframe_directions": {"15m": "LONG", "1H": "LONG"},
        }
        self.assertEqual(choose_forced_direction(result), "LONG")

    def test_forced_plan_has_directional_stops(self):
        settings = SimpleNamespace(
            stop_gap_min_usdt=400, stop_gap_max_usdt=700,
            take_profit_1_min_usdt=500, take_profit_1_max_usdt=600,
            take_profit_2_usdt=800,
        )
        long = build_forced_entry_result({}, 64000, "LONG", "MORNING", settings)
        short = build_forced_entry_result({}, 64000, "SHORT", "US", settings)
        self.assertEqual((long["stop_loss"], long["take_profit_1"]), (63450, 64550))
        self.assertEqual((short["stop_loss"], short["take_profit_1"]), (64550, 63450))


if __name__ == "__main__":
    unittest.main()
