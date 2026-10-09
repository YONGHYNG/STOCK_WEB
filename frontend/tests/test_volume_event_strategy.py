import math
import unittest
from unittest.mock import patch

import pandas as pd

from backend.strategy.volume_event_strategy import VolumeEventStrategy, classify_market


def base_candles(count=240):
    rows = []
    for i in range(count):
        center = 100 + math.sin(i / 4) * 0.4
        rows.append({
            "timestamp": i * 300_000,
            "open": center - 0.1,
            "high": center + 1.0,
            "low": center - 1.0,
            "close": center + 0.1,
            "volume": 100.0,
        })
    return rows


class VolumeEventStrategyTests(unittest.TestCase):
    def test_market_classifier_accepts_indicator_frame_trimmed_after_warmup(self):
        rows = []
        for i in range(12):
            recent = i >= 6
            rows.append({
                "high": 110 + i if recent else 100 + i,
                "low": 100 + i if recent else 90 + i,
                "close": 110 + i,
                "adx14": 28.0,
                "atr14": 2.0,
                "ema20": 108.0 + i,
                "ema50": 105.0 + i,
                "ema20_slope": 1.0,
                "ma90": 106.0,
                "ma200": 100.0,
                "ma90_slope": 0.5,
                "vwap": 105.0,
                "bb_width": 0.04,
            })
        self.assertEqual(classify_market(pd.DataFrame(rows)), "TREND_UP")

    def test_drop_recovery_confirms_mean_reversion_long(self):
        rows = base_candles()
        rows[-2].update(open=100, high=100.5, low=94, close=95, volume=500)
        rows[-1].update(open=95, high=98, low=94.5, close=97.5, volume=80)
        with patch("backend.strategy.volume_event_strategy.classify_market", return_value="RANGE"):
            decision = VolumeEventStrategy().evaluate(rows)
        self.assertEqual(decision.direction, "LONG", decision.reasons)
        self.assertEqual(decision.state, "REVERSAL_CONFIRMED")
        self.assertEqual(decision.strategy_signal, "LONG_VOLUME_MEAN_REVERSION")
        self.assertLess(decision.stop_loss, 94)
        self.assertEqual(decision.risk_reward_ratio, 2.0)

    def test_pump_rejection_confirms_mean_reversion_short(self):
        rows = base_candles()
        rows[-2].update(open=100, high=106, low=99.5, close=105, volume=500)
        rows[-1].update(open=105, high=105.5, low=101.5, close=102.5, volume=80)
        with patch("backend.strategy.volume_event_strategy.classify_market", return_value="RANGE"):
            decision = VolumeEventStrategy().evaluate(rows)
        self.assertEqual(decision.direction, "SHORT", decision.reasons)
        self.assertEqual(decision.state, "REVERSAL_CONFIRMED")

    def test_event_without_confirmation_becomes_no_trade_after_three_bars(self):
        rows = base_candles()
        rows[-4].update(open=100, high=100.5, low=94, close=95, volume=500)
        rows[-3].update(open=95, high=96, low=94.5, close=95.2, volume=80)
        rows[-2].update(open=95.2, high=96, low=94.6, close=95.1, volume=80)
        rows[-1].update(open=95.1, high=96, low=94.7, close=95.0, volume=80)
        with patch("backend.strategy.volume_event_strategy.classify_market", return_value="RANGE"):
            decision = VolumeEventStrategy().evaluate(rows)
        self.assertEqual(decision.direction, "NO_TRADE")
        self.assertEqual(decision.state, "NO_TRADE")

    def test_unknown_market_never_forces_direction(self):
        rows = base_candles()
        rows[-2].update(open=100, high=100.5, low=94, close=95, volume=500)
        rows[-1].update(open=95, high=98, low=94.5, close=97.5, volume=80)
        with patch("backend.strategy.volume_event_strategy.classify_market", return_value="UNKNOWN"):
            decision = VolumeEventStrategy().evaluate(rows)
        self.assertEqual(decision.direction, "NO_TRADE")
        self.assertEqual(decision.market_regime, "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
