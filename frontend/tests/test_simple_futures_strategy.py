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
from backend.order.sizing import (
    entry_price_deviation_pct,
    full_balance_size,
    normalize_limit_price,
)
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
                "adx14": 30.0,
                "bb_lower": 90.0,
                "bb_mid": 100.0,
                "bb_upper": 110.0,
                "bb_width": 0.05,
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


def transitioning_frame(range_bars: int) -> pd.DataFrame:
    frame = strategy_frame("LONG")
    frame["adx14"] = 30.0
    frame["bb_lower"] = 90.0
    frame["bb_mid"] = 100.0
    frame["bb_upper"] = 110.0
    frame["bb_width"] = 0.05
    if range_bars:
        start = len(frame) - range_bars
        frame.loc[start:, "adx14"] = 16.0
        frame.loc[start:, "ema20"] = 100.0
        frame.loc[start:, "ema50"] = 100.1
        frame.loc[start:, "ema20_slope"] = 0.05
        frame.loc[start:, "bb_width"] = 0.02
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

    def test_relaxed_range_rsi_boundaries_create_more_setups(self):
        long_frame = range_frame("LONG")
        long_frame.loc[218, "rsi14"] = 41.5
        long_frame.loc[219, "rsi14"] = 43.0
        self.assertEqual(
            VolumeTrendRsiStrategy().evaluate(long_frame).direction,
            "LONG",
        )

        short_frame = range_frame("SHORT")
        short_frame.loc[218, "rsi14"] = 58.5
        short_frame.loc[219, "rsi14"] = 57.0
        self.assertEqual(
            VolumeTrendRsiStrategy().evaluate(short_frame).direction,
            "SHORT",
        )

    def test_confirmed_trend_adds_ema_vwap_pullback_entry(self):
        long_frame = strategy_frame("LONG")
        long_frame.loc[218, "rsi14"] = 59.0
        long_frame.loc[219, ["low", "high", "close", "rsi14"]] = [
            100.5, 104.0, 103.0, 60.0
        ]
        long_decision = VolumeTrendRsiStrategy().evaluate(long_frame)
        self.assertEqual(long_decision.signal, "LONG_TREND_CONTINUATION")
        self.assertEqual(long_decision.direction, "LONG")

        short_frame = strategy_frame("SHORT")
        short_frame.loc[218, "rsi14"] = 41.0
        short_frame.loc[219, ["low", "high", "close", "rsi14"]] = [
            96.0, 99.0, 97.0, 40.0
        ]
        short_decision = VolumeTrendRsiStrategy().evaluate(short_frame)
        self.assertEqual(short_decision.signal, "SHORT_TREND_CONTINUATION")
        self.assertEqual(short_decision.direction, "SHORT")

    def test_breakout_retest_adds_long_and_short_entries_without_chasing(self):
        long_frame = strategy_frame("LONG")
        long_frame.loc[216, "adx14"] = 24.0
        long_frame.loc[217, ["low", "high", "close"]] = [100.0, 112.0, 111.0]
        long_frame.loc[217, "volume_ratio"] = 2.5
        long_frame.loc[217, "adx14"] = 30.0
        long_frame.loc[218, ["close", "rsi14"]] = [100.0, 60.0]
        long_frame.loc[219, ["low", "high", "close", "rsi14"]] = [
            109.5, 111.0, 110.5, 61.0
        ]
        long_decision = VolumeTrendRsiStrategy().evaluate(long_frame)
        self.assertEqual(long_decision.signal, "LONG_BREAKOUT_RETEST")
        self.assertEqual(long_decision.breakout_level, 110.0)

        short_frame = strategy_frame("SHORT")
        short_frame.loc[216, "adx14"] = 24.0
        short_frame.loc[217, ["low", "high", "close"]] = [88.0, 100.0, 89.0]
        short_frame.loc[217, "volume_ratio"] = 2.5
        short_frame.loc[217, "adx14"] = 30.0
        short_frame.loc[218, ["close", "rsi14"]] = [100.0, 40.0]
        short_frame.loc[219, ["low", "high", "close", "rsi14"]] = [
            89.0, 90.5, 89.5, 39.0
        ]
        short_decision = VolumeTrendRsiStrategy().evaluate(short_frame)
        self.assertEqual(short_decision.signal, "SHORT_BREAKOUT_RETEST")
        self.assertEqual(short_decision.breakout_level, 90.0)

        chase_frame = strategy_frame("LONG")
        chase_frame.loc[218, "adx14"] = 24.0
        chase_frame.loc[219, ["low", "high", "close", "rsi14"]] = [
            100.0, 112.0, 111.0, 61.0
        ]
        chase_frame.loc[219, "volume_ratio"] = 2.5
        chase_frame.loc[219, "adx14"] = 30.0
        chase_decision = VolumeTrendRsiStrategy().evaluate(chase_frame)
        self.assertEqual(chase_decision.direction, "HOLD")
        self.assertIn("추격 진입 금지", chase_decision.reasons[0])

    def test_regime_changes_only_after_three_confirmed_five_minute_bars(self):
        strategy = VolumeTrendRsiStrategy()
        self.assertEqual(strategy.evaluate(transitioning_frame(0)).market_regime, "TREND")

        first = strategy.evaluate(transitioning_frame(1))
        repeated = strategy.evaluate(transitioning_frame(1))
        second = strategy.evaluate(transitioning_frame(2))
        third = strategy.evaluate(transitioning_frame(3))

        self.assertEqual(first.market_regime, "TREND")
        self.assertEqual(first.raw_market_regime, "RANGE")
        self.assertEqual(first.regime_confirmation_count, 1)
        self.assertTrue(first.regime_transition_pending)
        self.assertEqual(repeated.regime_confirmation_count, 1)
        self.assertEqual(second.market_regime, "TREND")
        self.assertEqual(second.regime_confirmation_count, 2)
        self.assertEqual(third.market_regime, "RANGE")
        self.assertFalse(third.regime_transition_pending)

        back_to_trend = range_frame("LONG")
        back_to_trend.loc[219, "adx14"] = 30.0
        back_to_trend.loc[219, "bb_width"] = 0.05
        back_to_trend.loc[219, "ema20"] = 102.0
        back_to_trend.loc[219, "ema50"] = 100.0
        back_to_trend.loc[219, "ema20_slope"] = 1.0
        back_to_trend.loc[219, "vwap"] = 99.0
        back_to_trend.loc[219, "close"] = 105.0
        restarted_strategy = VolumeTrendRsiStrategy()
        restored = restarted_strategy.evaluate(back_to_trend)
        self.assertEqual(restored.raw_market_regime, "TREND_UP")
        self.assertEqual(restored.market_regime, "RANGE")
        self.assertEqual(restored.regime_confirmation_count, 1)

    def test_two_point_five_x_volume_breakout_blocks_opposite_range_entry(self):
        frame = range_frame("SHORT")
        # 직전 확정봉에서 상단을 2.5배 거래량으로 강하게 돌파한 뒤,
        # 현재 봉이 밴드 안으로 돌아와도 횡보 SHORT 반대매매를 막는다.
        frame.loc[217, "adx14"] = 18.0
        frame.loc[218, "close"] = 111.0
        frame.loc[218, "high"] = 112.0
        frame.loc[218, "volume_ratio"] = 2.5
        frame.loc[218, "adx14"] = 23.0
        frame.loc[218, "ema20_slope"] = 0.5
        frame.loc[218, "rsi14"] = 66.0
        frame.loc[219, "close"] = 108.0
        frame.loc[219, "high"] = 110.0
        frame.loc[219, "rsi14"] = 61.0

        decision = VolumeTrendRsiStrategy().evaluate(frame)

        self.assertEqual(decision.market_regime, "RANGE")
        self.assertEqual(decision.breakout_direction, "UP")
        self.assertEqual(decision.direction, "HOLD")
        self.assertIn("상단 강한 돌파 후 횡보 SHORT 진입 차단", decision.reasons)

    def test_less_than_two_point_five_x_volume_does_not_trigger_breakout_filter(self):
        frame = range_frame("SHORT")
        frame.loc[217, "adx14"] = 18.0
        frame.loc[218, "close"] = 111.0
        frame.loc[218, "high"] = 112.0
        frame.loc[218, "volume_ratio"] = 2.49
        frame.loc[218, "adx14"] = 23.0
        frame.loc[218, "ema20_slope"] = 0.5
        frame.loc[218, "rsi14"] = 66.0
        frame.loc[219, "close"] = 108.0
        frame.loc[219, "high"] = 110.0
        frame.loc[219, "rsi14"] = 61.0

        decision = VolumeTrendRsiStrategy().evaluate(frame)

        self.assertEqual(decision.breakout_direction, "HOLD")
        self.assertEqual(decision.direction, "SHORT")

    def test_neutral_market_does_not_fall_through_to_trend_strategy(self):
        frame = strategy_frame("LONG")
        frame.loc[219, "adx14"] = 22.5
        frame.loc[219, "ema20_slope"] = 0.2
        frame.loc[219, "bb_width"] = 0.04

        decision = VolumeTrendRsiStrategy().evaluate(frame)

        self.assertEqual(decision.raw_market_regime, "NEUTRAL")
        self.assertEqual(decision.direction, "HOLD")
        self.assertTrue(decision.regime_transition_pending)
        self.assertIn("신규 진입 대기", decision.reasons[0])

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

    def test_exchange_cost_buffer_and_price_tick_are_applied(self):
        size = full_balance_size(
            available_usdt=100,
            leverage=20,
            entry_price=65000,
            size_step="0.001",
            minimum_size="0.001",
            minimum_notional="5",
            fee_rate="0.0004",
            open_cost_up_ratio="0.1",
        )
        self.assertEqual(size, "0.027")
        self.assertEqual(normalize_limit_price("65000.17", 1, 1, "buy"), "65000.1")
        self.assertEqual(normalize_limit_price("65000.17", 1, 1, "sell"), "65000.2")
        self.assertAlmostEqual(
            entry_price_deviation_pct(65000, 65130),
            0.2,
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

    def test_order_detail_uses_the_pending_order_id(self):
        client = BitgetPrivateClient("key", "secret", "passphrase")
        captured = {}

        def fake_get(path, params):
            captured["path"] = path
            captured["params"] = params
            return {
                "data": {
                    "orderId": "entry-order",
                    "state": "partially_filled",
                    "baseVolume": "0.012",
                }
            }

        client._get = fake_get
        detail = client.get_order_detail("entry-order")

        self.assertEqual(captured["path"], "/api/v2/mix/order/detail")
        self.assertEqual(captured["params"]["orderId"], "entry-order")
        self.assertEqual(detail["state"], "partially_filled")
        self.assertEqual(detail["baseVolume"], "0.012")

    def test_recovery_apis_and_client_order_id_payloads(self):
        client = BitgetPrivateClient("key", "secret", "passphrase")
        get_calls = []
        post_calls = []

        def fake_get(path, params):
            get_calls.append((path, params))
            if path.endswith("orders-pending"):
                return {"data": {"entrustedList": [{"orderId": "pending-1"}]}}
            return {"data": {"list": [{"positionId": "position-1"}]}}

        def fake_post(path, body):
            post_calls.append((path, body))
            return {"data": {"orderId": "entry-1", "clientOid": body["clientOid"]}}

        client._get = fake_get
        client._post = fake_post

        self.assertEqual(client.get_pending_orders()[0]["orderId"], "pending-1")
        self.assertEqual(
            client.get_position_history(limit=20)[0]["positionId"],
            "position-1",
        )
        client.place_limit_order(
            "buy", "0.030", "65000.0", "open", client_oid="btc-auto-1"
        )

        self.assertEqual(get_calls[0][0], "/api/v2/mix/order/orders-pending")
        self.assertEqual(get_calls[1][0], "/api/v2/mix/position/history-position")
        self.assertEqual(post_calls[0][1]["clientOid"], "btc-auto-1")


class LiveExecutionDatabaseTests(unittest.TestCase):
    def test_execution_state_and_exchange_fills_are_persisted(self):
        original_data_dir = database.DATA_DIR
        original_db_path = database.DB_PATH
        with tempfile.TemporaryDirectory() as tmp:
            try:
                database.DATA_DIR = Path(tmp)
                database.DB_PATH = Path(tmp) / "trading.db"
                database.init_db()
                database.save_live_execution_state(
                    symbol="BTCUSDT",
                    order_id="entry-1",
                    client_oid="btc-auto-1",
                    direction="LONG",
                    planned_entry=65000,
                    stop_loss=64500,
                    take_profit=65600,
                    order_created_ms=1000,
                )
                state = database.get_live_execution_state("BTCUSDT")
                self.assertEqual(state["order_id"], "entry-1")

                opened = database.sync_live_position(
                    "BTCUSDT",
                    {
                        "holdSide": "long",
                        "openPriceAvg": "65010",
                        "total": "0.030",
                        "deductedFee": "0.58",
                        "cTime": "position-ctime-1",
                    },
                    state,
                    entry_order_id="entry-1",
                )
                self.assertEqual(opened["entry_price"], 65010)
                self.assertEqual(opened["size_btc"], 0.03)
                self.assertEqual(opened["entry_fee"], 0.58)
                self.assertEqual(opened["exchange_position_id"], "position-ctime-1")

                closed = database.sync_closed_live_position(
                    "BTCUSDT",
                    {
                        "positionId": "history-id",
                        "ctime": "position-ctime-1",
                        "holdSide": "long",
                        "openAvgPrice": "65010",
                        "closeAvgPrice": "65600",
                        "openTotalPos": "0.030",
                        "pnl": "17.7",
                        "netProfit": "16.4",
                        "totalFunding": "-0.1",
                        "openFee": "-0.58",
                        "closeFee": "-0.62",
                    },
                )
                self.assertEqual(closed["result"], "TP1")
                self.assertEqual(closed["exit_price"], 65600)
                self.assertEqual(closed["entry_fee"], 0.58)
                self.assertEqual(closed["exit_fee"], 0.62)
                self.assertEqual(closed["funding_fee"], -0.1)
                self.assertEqual(closed["net_profit"], 16.4)

                database.clear_live_execution_state("BTCUSDT")
                self.assertIsNone(database.get_live_execution_state("BTCUSDT"))

                snapshot = database.get_live_risk_snapshot()
                self.assertEqual(snapshot["today_net_profit"], 16.4)
                self.assertEqual(snapshot["consecutive_losses"], 0)
                database.set_live_emergency_stop(True, "청산 실패")
                snapshot = database.get_live_risk_snapshot()
                self.assertTrue(snapshot["emergency_stopped"])
                self.assertEqual(snapshot["emergency_reason"], "청산 실패")
            finally:
                database.DATA_DIR = original_data_dir
                database.DB_PATH = original_db_path

    def test_risk_manager_restores_actual_net_loss(self):
        manager = RiskManager(
            RiskSettings(
                daily_max_loss_pct=3.0,
                consecutive_loss_limit=3,
                live_trading_allowed=True,
            )
        )
        manager.restore_live_risk(
            today_net_profit=-4.0,
            account_equity=96.0,
            consecutive_losses=3,
            emergency_stopped=False,
        )
        allowed, reason = manager.check_entry(
            direction="LONG",
            confidence=100,
            mode=TradingMode.LIVE_TRADING,
            cached_positions=[],
            private_client=object(),
            entry_grade="A",
        )
        self.assertFalse(allowed)
        self.assertTrue("연속" in reason or "일일 손실" in reason)


if __name__ == "__main__":
    unittest.main()
