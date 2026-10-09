import unittest
from datetime import datetime
from types import SimpleNamespace

from backend.scheduled_entries import (
    KST,
    active_scheduled_session,
    build_forced_entry_result,
    choose_consensus_direction,
    choose_forced_direction,
    direction_bias_score,
    reprice_scheduled_result,
    scheduled_session_bounds,
    seconds_until_session_end,
)


class ScheduledEntryTests(unittest.TestCase):
    def test_windows_and_overnight_session_date(self):
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 5, 59, tzinfo=KST)))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 6, 0, tzinfo=KST)), ("2026-08-19", "MORNING"))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 9, 10, tzinfo=KST)), ("2026-08-19", "MORNING"))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 9, 11, tzinfo=KST)))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 16, 59, tzinfo=KST)))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 17, 0, tzinfo=KST)), ("2026-08-19", "EVENING"))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 23, 30, tzinfo=KST)), ("2026-08-19", "EVENING"))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 23, 31, tzinfo=KST)))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 12, 0, tzinfo=KST)))

    def test_weekend_keeps_two_daily_sessions(self):
        self.assertEqual(
            active_scheduled_session(datetime(2026, 8, 22, 6, 0, tzinfo=KST)),
            ("2026-08-22", "MORNING"),
        )
        self.assertEqual(
            active_scheduled_session(datetime(2026, 8, 23, 23, 0, tzinfo=KST)),
            ("2026-08-23", "EVENING"),
        )

    def test_session_bounds_and_remaining_time(self):
        morning_start, morning_end = scheduled_session_bounds("2026-08-19", "MORNING")
        self.assertEqual((morning_start.hour, morning_start.minute), (6, 0))
        self.assertEqual((morning_end.hour, morning_end.minute), (9, 10))
        self.assertEqual(
            seconds_until_session_end(
                "2026-08-19", "MORNING", datetime(2026, 8, 19, 9, 9, tzinfo=KST)
            ),
            60,
        )
        evening_start, evening_end = scheduled_session_bounds("2026-08-19", "EVENING")
        self.assertEqual((evening_start.hour, evening_start.minute), (17, 0))
        self.assertEqual((evening_end.hour, evening_end.minute), (23, 30))

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
            atr_stop_multiplier=1.5,
        )
        long = build_forced_entry_result({}, 64000, "LONG", "MORNING", settings)
        short = build_forced_entry_result({}, 64000, "SHORT", "EVENING", settings)
        self.assertEqual((long["stop_loss"], long["take_profit_1"]), (63475, 64525))
        self.assertEqual((short["stop_loss"], short["take_profit_1"]), (64525, 63475))
        self.assertEqual(long["risk_reward_ratio"], 1.0)
        self.assertNotIn("scalp_max_hold_seconds", long)
        self.assertNotIn("scalp_no_progress_seconds", long)

    def test_atr_controls_stop_distance_with_configured_bounds(self):
        settings = SimpleNamespace(
            stop_gap_min_usdt=400, stop_gap_max_usdt=700,
            take_profit_1_min_usdt=500, take_profit_1_max_usdt=600,
            take_profit_2_usdt=800, atr_stop_multiplier=1.5,
        )
        result = {"diagnostics": {"metrics": {"atr14": 400}}}
        plan = build_forced_entry_result(result, 64000, "LONG", "EVENING", settings)
        self.assertEqual(plan["stop_loss"], 63550)
        self.assertEqual(plan["take_profit_1"], 64450)

    def test_scalp_direction_prioritizes_five_and_fifteen_minute_frames(self):
        results = [{
            "direction": "SHORT", "long_probability": 30, "short_probability": 70,
            "timeframe_directions": {
                "5m": "SHORT", "15m": "HOLD", "1H": "LONG", "4H": "LONG", "6H": "LONG",
            },
        }]
        direction, _ = choose_consensus_direction(results)
        self.assertEqual(direction, "SHORT")

    def test_forced_direction_uses_one_hour_and_fifteen_minute_agreement(self):
        direction, _ = choose_consensus_direction([{
            "direction": "HOLD", "long_probability": 80, "short_probability": 20,
            "timeframe_directions": {"5m": "LONG", "15m": "SHORT", "1H": "SHORT"},
        }])
        self.assertEqual(direction, "SHORT")

    def test_split_fill_reprices_protection_from_average_entry(self):
        settings = SimpleNamespace(
            stop_gap_min_usdt=400, stop_gap_max_usdt=700,
            take_profit_1_min_usdt=500, take_profit_1_max_usdt=600,
            take_profit_2_usdt=800, atr_stop_multiplier=1.5,
        )
        initial = build_forced_entry_result({}, 68000, "LONG", "EVENING", settings)
        self.assertEqual(initial["stop_loss"], 67475)
        repriced = reprice_scheduled_result(initial, 67725)
        self.assertEqual(repriced["stop_loss"], 67200)
        self.assertEqual(repriced["take_profit_1"], 68250)
        self.assertEqual(repriced["take_profit_2"], 68775)

    def test_consensus_uses_multiple_analyses_and_recent_weight(self):
        results = [
            {"direction": "HOLD", "long_probability": 60, "short_probability": 40},
            {"direction": "SHORT", "long_probability": 42, "short_probability": 58},
            {"direction": "SHORT", "long_probability": 45, "short_probability": 55},
        ]
        direction, score = choose_consensus_direction(results)
        self.assertEqual(direction, "SHORT")
        self.assertLess(score, 0)

    def test_confirmed_direction_has_stronger_bias_than_hold(self):
        hold = {"direction": "HOLD", "long_probability": 55, "short_probability": 45}
        confirmed = {"direction": "LONG", "long_probability": 55, "short_probability": 45}
        self.assertGreater(direction_bias_score(confirmed), direction_bias_score(hold))


if __name__ == "__main__":
    unittest.main()
