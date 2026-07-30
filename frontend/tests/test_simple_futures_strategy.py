import json
import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd

import backend.database as database
from backend.order.paper_trader import PaperTrader
from backend.bitget.client import BitgetPrivateClient
from backend.risk.risk_manager import RiskManager
from backend.risk.settings import RiskSettings
from backend.order.sizing import full_balance_size
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


def range_frame(direction: str) -> pd.DataFrame:
    frame = strategy_frame(direction)
    frame["ema20"] = 100.0
    frame["ema50"] = 100.1
    frame["ema20_slope"] = 0.05
    frame["adx14"] = 16.0
    frame["bb_lower"] = 90.0
    frame["bb_mid"] = 100.0
    frame["bb_upper"] = 110.0
    frame["bb_width"] = 0.02
    if direction == "LONG":
        frame.loc[218, ["low", "close", "rsi14"]] = [89.5, 90.0, 34.0]
        frame.loc[219, ["low", "close", "rsi14"]] = [90.0, 92.0, 39.0]
    else:
        frame.loc[218, ["high", "close", "rsi14"]] = [110.5, 110.0, 66.0]
        frame.loc[219, ["high", "close", "rsi14"]] = [110.0, 108.0, 61.0]
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

    def test_range_lower_band_reversal_opens_long(self):
        decision = VolumeTrendRsiStrategy().evaluate(range_frame("LONG"))
        self.assertEqual(decision.signal, "LONG_RANGE_REVERSION")
        self.assertEqual(decision.direction, "LONG")
        self.assertEqual(decision.market_regime, "RANGE")

    def test_range_upper_band_reversal_opens_short(self):
        decision = VolumeTrendRsiStrategy().evaluate(range_frame("SHORT"))
        self.assertEqual(decision.signal, "SHORT_RANGE_REVERSION")
        self.assertEqual(decision.direction, "SHORT")

    def test_range_target_is_middle_band(self):
        stop, tp1, tp2, rr = TradingAIEngine._range_risk_prices(
            "LONG", 92.0, 4.0, 90.0, 100.0, 110.0
        )
        self.assertEqual((stop, tp1, tp2), (89.0, 100.0, 110.0))
        self.assertGreater(rr, 1.0)

    def test_reference_target_never_replaces_full_exit_target(self):
        trader = PaperTrader()
        trader._open_id = 1
        trader._open_data = {
            "direction": "LONG",
            "entry": 100.0,
            "sl": 90.0,
            "tp1": 110.0,
            "tp2": 120.0,
        }
        self.assertEqual(trader.check_tp_sl(125.0), "TP1")

    def test_entry_grade_uses_real_score_bands(self):
        self.assertEqual(TradingAIEngine._entry_grade(80.0), "A")
        self.assertEqual(TradingAIEngine._entry_grade(65.0), "B")
        self.assertEqual(TradingAIEngine._entry_grade(50.0), "C")
        self.assertEqual(TradingAIEngine._entry_grade(49.9), "F")

    def test_range_quality_score_rewards_stable_range(self):
        frame = range_frame("LONG")
        decision = VolumeTrendRsiStrategy().evaluate(frame)
        score = TradingAIEngine._signal_score(
            decision=decision,
            last=frame.iloc[-1],
            previous=frame.iloc[-2],
            direction="LONG",
            strong_15m="HOLD",
            volume_ratio=0.9,
            oi_confirmed=False,
            risk_reward=1.5,
            retest_distance=0.0,
            entry_atr=10.0,
        )
        self.assertGreaterEqual(score, 80.0)

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


class SignalDiagnosticsDatabaseTests(unittest.TestCase):
    def test_signal_diagnostics_are_persisted(self):
        original_data_dir = database.DATA_DIR
        original_db_path = database.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                database.DATA_DIR = Path(tmp)
                database.DB_PATH = Path(tmp) / "trading.db"
                database.init_db()
                database.insert_signal(
                    "BTCUSDT",
                    "5m",
                    {
                        "timestamp": 1,
                        "entry_price": 100.0,
                        "direction": "HOLD",
                        "confidence": 0.0,
                        "market_mode": "RANGE",
                        "strategy_signal": "HOLD",
                        "entry_grade": "F",
                        "diagnostics": {
                            "failed_conditions": {
                                "long": ["rsi_turn_up_near_50"],
                            },
                        },
                        "block_reasons": ["횡보장 밴드 반전 조건 대기"],
                    },
                )
                database.insert_signal(
                    "BTCUSDT",
                    "5m",
                    {
                        "timestamp": 1,
                        "entry_price": 101.0,
                        "direction": "LONG",
                        "confidence": 72.0,
                        "market_mode": "RANGE",
                        "strategy_signal": "LONG_RANGE_REVERSION",
                        "entry_grade": "B",
                        "diagnostics": {
                            "failed_conditions": {"long": []},
                        },
                        "block_reasons": [],
                    },
                )
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT market_regime, entry_grade, diagnostics_json, block_reason "
                        "FROM signals ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    count = conn.execute("SELECT COUNT(*) AS n FROM signals").fetchone()["n"]
                self.assertEqual(count, 1)
                self.assertEqual(row["market_regime"], "RANGE")
                self.assertEqual(row["entry_grade"], "B")
                self.assertEqual(
                    json.loads(row["diagnostics_json"])["failed_conditions"]["long"],
                    [],
                )
                self.assertEqual(row["block_reason"], "")

                # 같은 확정 봉을 다시 분석해 HOLD가 나오더라도 이미 기록된
                # 실행 가능 신호를 지우면 안 된다.
                database.insert_signal(
                    "BTCUSDT",
                    "5m",
                    {
                        "timestamp": 1,
                        "entry_price": 102.0,
                        "direction": "HOLD",
                        "confidence": 0.0,
                        "market_mode": "RANGE",
                        "strategy_signal": "HOLD",
                        "entry_grade": "F",
                        "diagnostics": {"failed_conditions": {"long": ["rsi_consumed"]}},
                        "block_reasons": ["이미 소비된 RSI 신호"],
                    },
                )
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT direction, entry_price, confidence, entry_grade, "
                        "strategy_signal, block_reason FROM signals WHERE timestamp=1"
                    ).fetchone()
                self.assertEqual(row["direction"], "LONG")
                self.assertEqual(row["entry_price"], 101.0)
                self.assertEqual(row["confidence"], 72.0)
                self.assertEqual(row["entry_grade"], "B")
                self.assertEqual(row["strategy_signal"], "LONG_RANGE_REVERSION")
                self.assertEqual(row["block_reason"], "")

                # 더 강한 등급은 갱신하고, 이후 들어온 약한 등급은 보존한다.
                database.insert_signal(
                    "BTCUSDT",
                    "5m",
                    {
                        "timestamp": 1,
                        "entry_price": 103.0,
                        "direction": "LONG",
                        "confidence": 85.0,
                        "market_mode": "TREND",
                        "strategy_signal": "LONG_TREND",
                        "entry_grade": "A",
                    },
                )
                database.insert_signal(
                    "BTCUSDT",
                    "5m",
                    {
                        "timestamp": 1,
                        "entry_price": 104.0,
                        "direction": "SHORT",
                        "confidence": 90.0,
                        "market_mode": "RANGE",
                        "strategy_signal": "SHORT_RANGE_REVERSION",
                        "entry_grade": "B",
                    },
                )
                with database.get_connection() as conn:
                    row = conn.execute(
                        "SELECT direction, entry_price, confidence, entry_grade, "
                        "strategy_signal FROM signals WHERE timestamp=1"
                    ).fetchone()
                self.assertEqual(row["direction"], "LONG")
                self.assertEqual(row["entry_price"], 103.0)
                self.assertEqual(row["confidence"], 85.0)
                self.assertEqual(row["entry_grade"], "A")
                self.assertEqual(row["strategy_signal"], "LONG_TREND")
            finally:
                database.DATA_DIR = original_data_dir
                database.DB_PATH = original_db_path


class LiveOrderSizingTests(unittest.TestCase):
    def test_full_balance_20x_size_is_rounded_down_to_contract_step(self):
        self.assertEqual(
            full_balance_size(
                available_usdt=100,
                leverage=20,
                entry_price=65000,
                size_step="0.001",
                minimum_size="0.001",
            ),
            "0.030",
        )

    def test_full_balance_size_rejects_below_minimum(self):
        with self.assertRaisesRegex(ValueError, "최소 주문 수량"):
            full_balance_size(
                available_usdt=1,
                leverage=20,
                entry_price=65000,
                size_step="0.001",
                minimum_size="0.001",
            )

    def test_position_tpsl_protects_the_entire_position_at_market(self):
        client = BitgetPrivateClient("key", "secret", "passphrase")
        captured = {}

        def fake_post(path, body):
            captured["path"] = path
            captured["body"] = body
            return {
                "data": [
                    {"orderId": "tp-order"},
                    {"orderId": "sl-order"},
                ]
            }

        client._post = fake_post
        result = client.place_position_tpsl("long", "66000.0", "64500.0")

        self.assertEqual(captured["path"], "/api/v2/mix/order/place-pos-tpsl")
        self.assertNotIn("stopSurplusSize", captured["body"])
        self.assertNotIn("stopLossSize", captured["body"])
        self.assertEqual(captured["body"]["stopSurplusExecutePrice"], "0")
        self.assertEqual(captured["body"]["stopLossExecutePrice"], "0")
        self.assertEqual([row["orderId"] for row in result], ["tp-order", "sl-order"])


if __name__ == "__main__":
    unittest.main()
