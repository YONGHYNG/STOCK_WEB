import unittest
import sqlite3
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd

from backend.strategy.entry_timing import (
    BAR_MS, ENTRY_TIMING_LOOKBACK_BARS, assess_entry_timing,
    timing_entry_check, scheduled_timing_check,
)


def frame_for(side="LONG", structural=False):
    rows = [dict(timestamp=1_800_000_000_000 + i * BAR_MS,
                 open=100., high=103., low=98., close=102., atr14=10.,
                 ema20=100., vwap=99.) for i in range(90)]
    if structural:
        rows[-3].update(open=102., high=107., low=101., close=106.)
        rows[-2].update(open=106., high=105., low=103., close=104.)
        rows[-1].update(open=104., high=108., low=104., close=107.)
    else:
        rows[-3].update(open=102., high=106., low=102., close=105.)
        rows[-2].update(open=105., high=103., low=100., close=101.)
        rows[-1].update(open=101., high=105., low=101., close=104.)
    # Keep OHLC internally consistent, including pullback candle opens.
    rows[-2]["open"] = rows[-2]["high"]
    df = pd.DataFrame(rows)
    if side == "SHORT":
        high, low = df.high.copy(), df.low.copy()
        for key in ("open", "close", "ema20", "vwap"):
            df[key] = 200 - df[key]
        df["high"], df["low"] = 200 - low, 200 - high
    return df


class EntryTimingTests(unittest.TestCase):
    def test_entry_timing_uses_sixty_completed_five_minute_bars(self):
        frame = frame_for()
        self.assertEqual(ENTRY_TIMING_LOOKBACK_BARS, 60)
        self.assertFalse(
            assess_entry_timing(frame.iloc[-59:], "LONG", {})["confirmed"]
        )
        self.assertTrue(
            assess_entry_timing(frame.iloc[-60:], "LONG", {})["confirmed"]
        )

    def test_touch_alone_does_not_confirm_but_restart_does_both_sides(self):
        for side in ("LONG", "SHORT"):
            frame = frame_for(side)
            self.assertFalse(assess_entry_timing(frame.iloc[:-1], side, {})["confirmed"])
            result = assess_entry_timing(frame, side, {})
            self.assertTrue(result["confirmed"], result)
            self.assertEqual(result["kind"], "PULLBACK_CONFIRMATION")

    def test_countertrend_requires_break_then_separate_retest(self):
        for side, other in (("LONG", "SHORT"), ("SHORT", "LONG")):
            self.assertFalse(assess_entry_timing(frame_for(side), side, {"30m": other})["confirmed"])
            frame = frame_for(side, True)
            result = assess_entry_timing(frame, side, {"30m": other, "1H": other})
            self.assertTrue(result["confirmed"], result)
            self.assertEqual(result["kind"], "STRUCTURE_RETEST")
            self.assertFalse(assess_entry_timing(frame.iloc[:-2], side, {"1H": other})["confirmed"])

    def test_no_chasing_after_confirmation_or_structure_failure(self):
        for side, sign in (("LONG", 1), ("SHORT", -1)):
            result = assess_entry_timing(frame_for(side), side, {})
            price = result["confirmation_price"]
            now = result["timestamp"] + BAR_MS + 1000
            self.assertTrue(timing_entry_check(result, price, now)[0])
            self.assertFalse(timing_entry_check(result, price + sign * 3, now)[0])
            self.assertFalse(timing_entry_check(result, result["invalidation_price"], now)[0])
            self.assertFalse(timing_entry_check(result, float("nan"), now)[0])

    def test_profit_reentry_requires_setup_started_after_exit(self):
        result = assess_entry_timing(frame_for(), "LONG", {})
        stamp = result["setup_start"]
        def exit_at(ms):
            return dict(direction="LONG", pnl_pct=.5,
                        exit_time=datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        self.assertFalse(timing_entry_check(result, 104, last_exit=exit_at(stamp + 1000))[0])
        self.assertTrue(timing_entry_check(result, 104, last_exit=exit_at(stamp - 1000))[0])
        loss = exit_at(stamp + 1000)
        loss["pnl_pct"] = -.5
        self.assertTrue(timing_entry_check(result, 104, last_exit=loss)[0])

    def test_stale_unfinished_missing_and_gapped_candles_fail_closed(self):
        frame = frame_for()
        result = assess_entry_timing(frame, "LONG", {})
        for now in (result["timestamp"], result["timestamp"] + 2 * BAR_MS):
            self.assertFalse(timing_entry_check(result, 104, now)[0])
        self.assertFalse(timing_entry_check({}, 104)[0])
        frame.loc[55, "timestamp"] += 1
        self.assertFalse(assess_entry_timing(frame, "LONG", {})["confirmed"])

    def test_deadline_override_is_explicit_and_only_at_deadline(self):
        timing = {"confirmed": False, "reason": "구조 전환 대기"}
        self.assertEqual(scheduled_timing_check(timing, 100, False, 0)[:2], (False, "WAIT"))
        allowed, status, reason = scheduled_timing_check(timing, 100, True, 0)
        self.assertTrue(allowed)
        self.assertEqual(status, "DEADLINE_OVERRIDE")
        self.assertIn("구조 전환 대기", reason)


class EngineTimingTests(unittest.TestCase):
    def test_engine_gates_candidates_and_uses_confirmation_price(self):
        from backend.strategy.volume_trend_engine import TradingAIEngine
        from backend.strategy.strategy import StrategyDecision
        from backend.risk.settings import RiskSettings
        from test_simple_futures_strategy import strategy_frame
        engine = TradingAIEngine()
        frame = strategy_frame("LONG")
        tail = frame_for()
        for key in tail.columns:
            frame.loc[130:219, key] = tail[key].to_numpy()
        candidate = StrategyDecision("LONG_RSI_RECLAIM", "LONG", "READY", 104, None, None, [], [])
        raw = [{"timestamp": i} for i in range(221)]
        frames = {"directions": {"5m": "LONG"}, "summaries": {}}
        with patch.object(engine.strategy, "evaluate", return_value=candidate), \
             patch.object(engine, "_analyze_frames", return_value=frames), \
             patch("backend.strategy.volume_trend_engine.add_indicators", return_value=frame) as indicators, \
             patch("backend.strategy.volume_trend_engine.load_risk_settings", return_value=RiskSettings()):
            result = engine.analyze_multi_timeframe({"5m": raw}, market={"last_price": 104})
            self.assertEqual(indicators.call_args_list[0].args[0], raw[:-1])
            self.assertEqual(result.direction, "LONG", result.reasons)
            self.assertGreaterEqual(result.entry_price, 104)
            self.assertEqual(result.diagnostics["entry_timing"], result.entry_timing)
            frame.loc[219, "close"] = 102
            result = engine.analyze_multi_timeframe({"5m": raw}, market={"last_price": 102})
            self.assertEqual(result.direction, "HOLD")
            self.assertFalse(result.entry_timing["LONG"]["confirmed"])

    def test_last_exit_lookup_uses_persisted_execution_history_and_mode(self):
        import backend.database as db
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "test.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE trades (id INTEGER, symbol TEXT, trade_type TEXT, "
                         "direction TEXT, result TEXT, exit_time TEXT)")
            conn.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?)", [
                (1, "BTCUSDT", "PAPER", "LONG", "TP1", "2026-09-11 01:00:00"),
                (2, "BTCUSDT", "PLAN", "SHORT", "TP1", "2026-09-11 02:00:00"),
                (3, "BTCUSDT", "LIVE", "SHORT", "SL", "2026-09-11 03:00:00"),
                (4, "BTCUSDT", "PAPER", "SHORT", "OPEN", None),
            ])
            conn.commit()
            conn.close()
            def connect():
                connection = sqlite3.connect(path)
                connection.row_factory = sqlite3.Row
                return connection
            with patch.object(db, "get_connection", side_effect=connect):
                self.assertEqual(db.get_last_closed_trade("BTCUSDT", "PAPER")["id"], 1)
                self.assertEqual(db.get_last_closed_trade("BTCUSDT", "LIVE")["id"], 3)
                self.assertIsNone(db.get_last_closed_trade("ETHUSDT", "PAPER"))


class ServiceTimingTests(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_waits_then_records_deadline_exception(self):
        from api.services import trading_control_service as svc
        result = dict(direction="HOLD", confidence=0, entry_price=104,
                      timeframe_directions={"5m": "LONG", "15m": "LONG"},
                      entry_timing={"LONG": {"confirmed": False, "reason": "새 눌림 대기"}})
        fake_state = SimpleNamespace(trading_mode="PAPER_TRADING", auto_trade_enabled=True,
            emergency_stopped=False, last_price=104, last_result=result,
            pending_paper_order=None, pending_live_order=None, paper_account_start_trade_id=None,
            add_log=lambda message: message)
        trader = Mock(is_open=False)
        trader.open_trade.return_value = 77
        with patch.object(svc, "state", fake_state), patch.object(svc, "paper_trader", trader), \
             patch.object(svc, "_scheduled_analysis_runs", {}), \
             patch.object(svc, "get_scheduled_entry_session", return_value=None), \
             patch.object(svc, "get_last_closed_trade", return_value=None), \
             patch.object(svc, "_worker_analyze", return_value=(result, [])), \
             patch.object(svc, "seconds_until_session_end", return_value=590) as remaining, \
             patch.object(svc, "_paper_full_leverage_size", return_value=.02), \
             patch.object(svc, "risk_mgr", Mock()), \
             patch.object(svc, "_status_payload", return_value={}), \
             patch.object(svc, "manager", SimpleNamespace(broadcast=AsyncMock())), \
             patch.object(svc, "_send_filled_position_email", AsyncMock()):
            await svc._execute_scheduled_entry("2026-09-14", "EUROPE")
            trader.open_trade.assert_not_called()
            remaining.return_value = 30
            await svc._execute_scheduled_entry("2026-09-14", "EUROPE")
            trader.open_trade.assert_called_once()
            plan = trader.open_trade.call_args.args[1]
            self.assertEqual(plan["entry_timing_status"], "DEADLINE_OVERRIDE")
            self.assertIn("DEADLINE_OVERRIDE", "\n".join(plan["reasons"]))
            self.assertEqual(plan["entry_price"], 104)
            self.assertEqual(plan["position_size_btc"], .01)

    async def test_normal_entry_blocked_before_order_when_setup_predates_profit(self):
        from api.services import trading_control_service as svc
        timing = assess_entry_timing(frame_for(), "LONG", {})
        now = timing["timestamp"] + BAR_MS + 1000
        trade = dict(direction="LONG", pnl_pct=.5, exit_time=datetime.fromtimestamp(
            (timing["setup_start"] + 1000) / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        state = SimpleNamespace(auto_trade_enabled=True, trading_mode="PAPER_TRADING",
            last_price=104, pending_paper_order=None, add_log=lambda message: message)
        with patch.object(svc, "state", state), patch.object(svc, "active_scheduled_session", return_value=None), \
             patch.object(svc, "get_last_closed_trade", return_value=trade), \
             patch.object(svc.time, "time", return_value=now / 1000), \
             patch.object(svc, "manager", SimpleNamespace(broadcast=AsyncMock())), \
             patch.object(svc, "_auto_paper_trade", AsyncMock()) as order:
            await svc._check_auto_trade(dict(direction="LONG", confidence=85, entry_timing={"LONG": timing}))
            order.assert_not_called()

    async def test_confirmed_normal_entry_reaches_order_path(self):
        from api.services import trading_control_service as svc
        timing = assess_entry_timing(frame_for(), "LONG", {})
        now = timing["timestamp"] + BAR_MS + 1000
        state = SimpleNamespace(auto_trade_enabled=True, trading_mode="PAPER_TRADING",
            last_price=104, pending_paper_order=None, cached_positions=[], add_log=lambda message: message)
        risk = Mock()
        risk.check_entry.return_value = (True, "")
        with patch.object(svc, "state", state), patch.object(svc, "active_scheduled_session", return_value=None), \
             patch.object(svc, "get_last_closed_trade", return_value=None), \
             patch.object(svc.time, "time", return_value=now / 1000), \
             patch.object(svc, "risk_mgr", risk), patch.object(svc, "engine", Mock()), \
             patch.object(svc, "_auto_paper_trade", AsyncMock(return_value=True)) as order:
            await svc._check_auto_trade(dict(direction="LONG", confidence=85, entry_timing={"LONG": timing}))
            order.assert_awaited_once()

    async def test_pending_order_cannot_fill_after_structure_breaks(self):
        from api.services import trading_control_service as svc
        timing = assess_entry_timing(frame_for(), "LONG", {})
        now = timing["timestamp"] + BAR_MS + 1000
        result = dict(direction="LONG", confidence=85, entry_grade="A", entry_price=104,
                      entry_timing={"LONG": timing})
        state = SimpleNamespace(trading_mode="PAPER_TRADING", last_price=99,
            pending_paper_order={"direction": "LONG", "result": result},
            last_result=result, add_log=lambda message: message)
        trader = Mock(is_open=False)
        with patch.object(svc, "state", state), patch.object(svc, "paper_trader", trader), \
             patch.object(svc, "get_last_closed_trade", return_value=None), \
             patch.object(svc.time, "time", return_value=now / 1000), \
             patch.object(svc, "_status_payload", return_value={}), \
             patch.object(svc, "manager", SimpleNamespace(broadcast=AsyncMock())):
            await svc._check_pending_paper_entry(99)
            self.assertIsNone(state.pending_paper_order)
            trader.open_trade.assert_not_called()


if __name__ == "__main__":
    unittest.main()
