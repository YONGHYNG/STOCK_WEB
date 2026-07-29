import time
import unittest

import pandas as pd

from backend.risk.risk_manager import RiskManager
from backend.risk.settings import RiskSettings
from backend.strategy.strategy import VolumeTrendRsiStrategy
from backend.strategy.volume_trend_engine import TradingAIEngine
from backend.trading_modes import TradingMode


def strategy_frame(direction: str) -> pd.DataFrame:
    rows = []
    for index in range(220):
        rows.append(
            {
                "timestamp": index * 300_000,
                "open": 100.0,
                "high": 100.0,
                "low": 90.0,
                "close": 100.0,
                "volume": 100.0,
                "ema20": 102.0 if direction == "LONG" else 98.0,
                "ema50": 100.0,
                "ema20_slope": 1.0 if direction == "LONG" else -1.0,
                "ma90": 100.0,
                "vwap": 99.0 if direction == "LONG" else 101.0,
                "rsi14": 60.0 if direction == "LONG" else 40.0,
                "atr14": 10.0,
                "volume_ratio": 1.0,
            }
        )
    frame = pd.DataFrame(rows)
    if direction == "LONG":
        frame.loc[208:213, ["high", "low"]] = [100.0, 90.0]
        frame.loc[214:219, ["high", "low"]] = [110.0, 95.0]
        frame.loc[210, "rsi14"] = 46.0
        frame.loc[218, "rsi14"] = 49.0
        frame.loc[219, "rsi14"] = 51.0
    else:
        frame.loc[208:213, ["high", "low"]] = [110.0, 95.0]
        frame.loc[214:219, ["high", "low"]] = [100.0, 90.0]
        frame.loc[210, "rsi14"] = 54.0
        frame.loc[218, "rsi14"] = 51.0
        frame.loc[219, "rsi14"] = 49.0
    return frame


class StrategyTests(unittest.TestCase):
    def test_long_cycle_is_consumed_only_after_order(self):
        strategy = VolumeTrendRsiStrategy()
        frame = strategy_frame("LONG")
        self.assertEqual(strategy.evaluate(frame).direction, "LONG")
        self.assertEqual(strategy.evaluate(frame).direction, "LONG")
        strategy.consume("LONG", int(frame.iloc[-1]["timestamp"]))
        self.assertEqual(strategy.evaluate(frame).direction, "HOLD")

    def test_short_cycle_is_consumed_only_after_order(self):
        strategy = VolumeTrendRsiStrategy()
        frame = strategy_frame("SHORT")
        self.assertEqual(strategy.evaluate(frame).direction, "SHORT")
        self.assertEqual(strategy.evaluate(frame).direction, "SHORT")
        strategy.consume("SHORT", int(frame.iloc[-1]["timestamp"]))
        self.assertEqual(strategy.evaluate(frame).direction, "HOLD")

    def test_atr_stop_targets_and_position_size(self):
        stop, tp1, tp2, rr = TradingAIEngine._risk_prices("LONG", 100.0, 10.0, 1.5)
        self.assertEqual((stop, tp1, tp2, rr), (85.0, 115.0, 122.5, 1.5))
        self.assertEqual(TradingAIEngine._position_size(2.0, 100.0, 90.0, 0.001, 0.001), 0.2)

    def test_long_entry_waits_for_nearest_retest_support(self):
        entry, anchor, distance = TradingAIEngine._retest_entry(
            "LONG", market_entry=105.0, ema20=102.0, vwap=100.0, atr=10.0
        )
        self.assertEqual(anchor, "EMA20")
        self.assertEqual(entry, 102.75)
        self.assertEqual(distance, 2.25)

    def test_short_entry_waits_for_nearest_retest_resistance(self):
        entry, anchor, distance = TradingAIEngine._retest_entry(
            "SHORT", market_entry=95.0, ema20=98.0, vwap=101.0, atr=10.0
        )
        self.assertEqual(anchor, "EMA20")
        self.assertEqual(entry, 97.25)
        self.assertEqual(distance, 2.25)

    def test_retest_never_crosses_market_price(self):
        long_entry, _, _ = TradingAIEngine._retest_entry(
            "LONG", market_entry=100.0, ema20=99.9, vwap=90.0, atr=10.0
        )
        short_entry, _, _ = TradingAIEngine._retest_entry(
            "SHORT", market_entry=100.0, ema20=100.1, vwap=110.0, atr=10.0
        )
        self.assertEqual(long_entry, 100.0)
        self.assertEqual(short_entry, 100.0)

    def test_15m_strong_trend_requires_ma90_slope(self):
        self.assertEqual(
            TradingAIEngine._strong_direction(
                {"close": 120.0, "ma90": 110.0, "ma200": 100.0, "ma90_slope": 1.0}
            ),
            "LONG",
        )
        self.assertEqual(
            TradingAIEngine._strong_direction(
                {"close": 120.0, "ma90": 110.0, "ma200": 100.0, "ma90_slope": -1.0}
            ),
            "HOLD",
        )


class RiskManagerTests(unittest.TestCase):
    def setUp(self):
        self.manager = RiskManager(
            RiskSettings(
                stop_reentry_wait_seconds=900,
                take_profit_reentry_wait_seconds=300,
                two_loss_pause_seconds=3600,
            )
        )

    def test_tp_waits_five_minutes(self):
        before = time.time()
        self.manager.record_trade_result(1.0, "TP1")
        self.assertGreaterEqual(self.manager._entry_block_until, before + 299)

    def test_two_losses_pause_but_three_losses_do_not_stop_paper_trading(self):
        self.manager.record_trade_result(-1.0, "SL")
        self.manager.record_trade_result(-1.0, "SL")
        self.assertGreater(self.manager._entry_block_until, time.time() + 3590)
        self.manager.record_trade_result(-1.0, "SL")
        self.manager._entry_block_until = 0
        allowed, reason = self.manager.check_entry(
            direction="LONG",
            confidence=100,
            mode=TradingMode.PAPER_TRADING,
            cached_positions=[],
            private_client=None,
            entry_grade="A",
            strategy_signal="LONG_RSI_RECLAIM",
            timeframe_directions={"15m": "HOLD"},
        )
        self.assertTrue(allowed, reason)

    def test_15m_hold_is_allowed(self):
        allowed, reason = self.manager.check_entry(
            direction="LONG",
            confidence=100,
            mode=TradingMode.PAPER_TRADING,
            cached_positions=[],
            private_client=None,
            entry_grade="A",
            strategy_signal="LONG_RSI_RECLAIM",
            timeframe_directions={"15m": "HOLD"},
        )
        self.assertTrue(allowed, reason)


if __name__ == "__main__":
    unittest.main()
