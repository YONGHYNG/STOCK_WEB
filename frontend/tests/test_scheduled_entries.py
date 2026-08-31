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
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 8, 57, tzinfo=KST)))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 8, 58, tzinfo=KST)), ("2026-08-19", "MORNING"))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 9, 28, tzinfo=KST)), ("2026-08-19", "MORNING"))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 9, 29, tzinfo=KST)))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 16, 29, tzinfo=KST)))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 16, 30, tzinfo=KST)), ("2026-08-19", "EUROPE"))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 19, 17, 0, tzinfo=KST)), ("2026-08-19", "EUROPE"))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 17, 1, tzinfo=KST)))
        self.assertEqual(active_scheduled_session(datetime(2026, 8, 20, 0, 10, tzinfo=KST)), ("2026-08-19", "US"))
        self.assertIsNone(active_scheduled_session(datetime(2026, 8, 19, 12, 0, tzinfo=KST)))

    def test_session_bounds_and_remaining_time(self):
        morning_start, morning_end = scheduled_session_bounds("2026-08-19", "MORNING")
        self.assertEqual((morning_start.hour, morning_start.minute), (8, 58))
        self.assertEqual((morning_end.hour, morning_end.minute), (9, 28))
        self.assertEqual(
            seconds_until_session_end(
                "2026-08-19", "MORNING", datetime(2026, 8, 19, 9, 27, tzinfo=KST)
            ),
            60,
        )
        us_start, us_end = scheduled_session_bounds("2026-08-19", "US")
        self.assertEqual(us_start.date().isoformat(), "2026-08-19")
        self.assertEqual(us_end.date().isoformat(), "2026-08-20")

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
        short = build_forced_entry_result({}, 64000, "SHORT", "US", settings)
        self.assertEqual((long["stop_loss"], long["take_profit_1"]), (63450, 64715))
        self.assertEqual((short["stop_loss"], short["take_profit_1"]), (64550, 63285))
        self.assertEqual(long["risk_reward_ratio"], 1.3)

    def test_atr_controls_stop_distance_with_configured_bounds(self):
        settings = SimpleNamespace(
            stop_gap_min_usdt=400, stop_gap_max_usdt=700,
            take_profit_1_min_usdt=500, take_profit_1_max_usdt=600,
            take_profit_2_usdt=800, atr_stop_multiplier=1.5,
        )
        result = {"diagnostics": {"metrics": {"atr14": 400}}}
        plan = build_forced_entry_result(result, 64000, "LONG", "US", settings)
        self.assertEqual(plan["stop_loss"], 63400)
        self.assertEqual(plan["take_profit_1"], 64780)

    def test_higher_timeframes_override_short_term_countertrend(self):
        results = [{
            "direction": "SHORT", "long_probability": 30, "short_probability": 70,
            "timeframe_directions": {
                "5m": "SHORT", "15m": "HOLD", "1H": "LONG", "4H": "LONG", "6H": "LONG",
            },
        }]
        direction, _ = choose_consensus_direction(results)
        self.assertEqual(direction, "LONG")

    def test_split_fill_reprices_protection_from_average_entry(self):
        settings = SimpleNamespace(
            stop_gap_min_usdt=400, stop_gap_max_usdt=700,
            take_profit_1_min_usdt=500, take_profit_1_max_usdt=600,
            take_profit_2_usdt=800, atr_stop_multiplier=1.5,
        )
        initial = build_forced_entry_result({}, 68000, "LONG", "US", settings)
        self.assertEqual(initial["stop_loss"], 67450)
        repriced = reprice_scheduled_result(initial, 67725)
        self.assertEqual(repriced["stop_loss"], 67175)
        self.assertEqual(repriced["take_profit_1"], 68440)
        self.assertEqual(repriced["take_profit_2"], 68715)

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
