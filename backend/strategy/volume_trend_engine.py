# 역할: 거래량, 추세, RSI 전략을 기존 GUI/API 결과 형식으로 변환합니다.
from dataclasses import dataclass
from typing import Optional

from backend.config import SYMBOL, TAKER_FEE_RATE, TIMEFRAMES
from backend.strategy.indicator import add_indicators
from backend.strategy.strategy import VolumeTrendRsiStrategy
from backend.risk.settings import load as load_risk_settings

RISK_ATR_MULTIPLIER = 3.0
TAKE_PROFIT_1_R_MULTIPLIER = 1.0
TAKE_PROFIT_2_R_MULTIPLIER = 1.5
STRUCTURE_LOOKBACK = 60
STRUCTURE_STOP_BUFFER_ATR = 0.4
RISK_TIMEFRAMES = ("5m",)
LIMIT_ENTRY_OFFSET_USDT = 250.0


@dataclass
class TradingResult:
    timestamp: int
    entry_price: float
    direction: str
    long_probability: float
    short_probability: float
    confidence: float
    stop_loss: Optional[float]
    take_profit_1: Optional[float]
    take_profit_2: Optional[float]
    risk_reward_ratio: Optional[float]
    all_time_high_mode: bool
    all_time_low_mode: bool
    timeframe_directions: dict[str, str]
    reasons: list[str]
    analysis_price: float = 0.0
    last_price: Optional[float] = None
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    expected_entry_long: Optional[float] = None
    expected_entry_short: Optional[float] = None
    take_profit_3: Optional[float] = None
    long_score: float = 50.0
    short_score: float = 50.0
    entry_grade: str = "F"
    risk_warnings: Optional[list[str]] = None
    spread_rate: Optional[float] = None
    funding_rate: Optional[float] = None
    estimated_fee: Optional[float] = None
    estimated_funding_fee: Optional[float] = None
    net_risk_reward: Optional[float] = None
    position_size_btc: Optional[float] = None
    position_value: Optional[float] = None
    max_loss_usdt: Optional[float] = None
    leverage: int = 3
    liquidation_price: Optional[float] = None
    liquidation_gap: Optional[float] = None
    stop_gap: Optional[float] = None
    market_mode: str = "HOLD"
    position_size_ratio: float = 1.0
    timeframe_summary: Optional[dict[str, dict]] = None
    strategy_signal: str = "HOLD"
    planned_direction: str = "HOLD"

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["risk_warnings"] = d.get("risk_warnings") or []
        d["warnings"] = d["risk_warnings"]
        d["symbol"] = SYMBOL
        d["timeframe_summary"] = d.get("timeframe_summary") or {}
        return d


class TradingAIEngine:
    def __init__(self) -> None:
        self.strategy = VolumeTrendRsiStrategy()

    def analyze(
        self,
        candles: list[dict],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
        market: Optional[dict] = None,
        account_equity: Optional[float] = None,
    ) -> TradingResult:
        return self.analyze_multi_timeframe(
            {"5m": candles},
            all_time_high=all_time_high,
            all_time_low=all_time_low,
            market=market,
            account_equity=account_equity,
        )

    def analyze_multi_timeframe(
        self,
        candles_by_timeframe: dict[str, list[dict]],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
        market: Optional[dict] = None,
        account_equity: Optional[float] = None,
    ) -> TradingResult:
        candles = candles_by_timeframe.get("1m") or candles_by_timeframe.get("5m") or []
        market = market or {}
        df = add_indicators(candles)
        frame_info = self._analyze_frames(candles_by_timeframe)
        if len(df) < 220:
            last_price = float(df.iloc[-1]["close"]) if len(df) else 0.0
            return self._empty(last_price, "MA200 기반 전략 계산을 위한 확정 캔들이 부족합니다.", frame_info)

        decision = self.strategy.evaluate(df)
        last = df.iloc[-1]
        price = float(market.get("last_price") or decision.entry_price)
        pricing = self._pricing(price, market)
        direction = decision.direction
        plan_direction = self._plan_direction(decision.signal, direction)
        planned_entry = self._planned_entry(decision.signal, decision.support_level, decision.breakout_level, price)
        if direction == "LONG":
            entry = pricing["expected_entry_long"]
        elif direction == "SHORT":
            entry = pricing["expected_entry_short"]
        elif plan_direction in ("LONG", "SHORT") and planned_entry:
            entry = planned_entry
        else:
            entry = price
        if plan_direction == "LONG":
            entry -= LIMIT_ENTRY_OFFSET_USDT
        elif plan_direction == "SHORT":
            entry += LIMIT_ENTRY_OFFSET_USDT
        atr = float(last.get("atr14") or 0)
        stop_loss, tp1, tp2, rr = self._risk_prices(
            plan_direction, entry, atr, df, decision, last, frame_info["summaries"], load_risk_settings()
        )
        warnings = list(decision.warnings)
        entry_grade = self._entry_grade(
            direction=direction,
            signal=decision.signal,
            stop_loss=stop_loss,
            risk_reward=rr,
            volume_ratio=float(last.get("volume_ratio") or 0),
            timeframe_directions=frame_info["directions"],
        )
        if decision.signal.startswith("WAIT"):
            warnings.append("WAIT 상태: 시장가 추격 진입 금지")
            warnings.append("표시된 진입가/손절가/익절가는 조건 충족 시 사용할 예상 계획")
        if entry_grade in ("C", "D", "F"):
            final_direction = "HOLD"
        else:
            final_direction = direction

        long_score = 75.0 if direction == "LONG" else 25.0 if direction == "SHORT" else 50.0
        short_score = 75.0 if direction == "SHORT" else 25.0 if direction == "LONG" else 50.0
        confidence = 100.0 if final_direction in ("LONG", "SHORT") else 0.0
        reasons = decision.reasons + [f"전략 신호: {decision.signal}", "모든 판단은 확정 캔들 기준"]
        if decision.signal.startswith("WAIT") and plan_direction in ("LONG", "SHORT") and stop_loss and tp1:
            reasons.append(f"{plan_direction} 대기 계획: 예상 진입 ${entry:,.2f}, SL ${stop_loss:,.2f}, TP1 ${tp1:,.2f}")
        if warnings:
            reasons += [f"경고: {w}" for w in warnings]

        value = None
        size = None
        fee = None
        if final_direction in ("LONG", "SHORT") and stop_loss:
            max_loss = float(account_equity or 1000.0) * 0.005
            risk_per_unit = abs(entry - stop_loss)
            size = max_loss / risk_per_unit if risk_per_unit > 0 else None
            value = size * entry if size else None
            fee = value * float(market.get("fee_rate") or TAKER_FEE_RATE) * 2 if value else None

        return TradingResult(
            timestamp=int(last.get("timestamp") or 0),
            entry_price=round(entry, 2),
            direction=final_direction,
            long_probability=long_score,
            short_probability=short_score,
            confidence=confidence,
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            take_profit_1=round(tp1, 2) if tp1 else None,
            take_profit_2=round(tp2, 2) if tp2 else None,
            risk_reward_ratio=round(rr, 2) if rr else None,
            all_time_high_mode=bool(all_time_high and entry >= all_time_high),
            all_time_low_mode=bool(all_time_low and entry <= all_time_low),
            timeframe_directions=frame_info["directions"],
            reasons=reasons,
            analysis_price=round(price, 2),
            last_price=pricing["last_price"],
            mark_price=pricing["mark_price"],
            index_price=pricing["index_price"],
            best_bid=pricing["best_bid"],
            best_ask=pricing["best_ask"],
            expected_entry_long=pricing["expected_entry_long"],
            expected_entry_short=pricing["expected_entry_short"],
            long_score=long_score,
            short_score=short_score,
            entry_grade=entry_grade,
            risk_warnings=warnings,
            spread_rate=pricing["spread_rate"],
            funding_rate=market.get("funding_rate"),
            estimated_fee=round(fee, 4) if fee else None,
            estimated_funding_fee=None,
            net_risk_reward=round(rr, 2) if rr else None,
            position_size_btc=round(size, 6) if size else None,
            position_value=round(value, 2) if value else None,
            max_loss_usdt=round(float(account_equity or 1000.0) * 0.005, 2),
            leverage=int(market.get("leverage") or 3),
            liquidation_price=market.get("liquidation_price"),
            stop_gap=round(abs(entry - stop_loss) / entry, 4) if stop_loss and entry else None,
            market_mode=decision.state,
            timeframe_summary=self._timeframe_summary(frame_info["summaries"], last, decision, plan_direction, entry, stop_loss, tp1, tp2),
            strategy_signal=decision.signal,
            planned_direction=plan_direction,
        )

    @staticmethod
    def _entry_grade(
        direction: str,
        signal: str,
        stop_loss: Optional[float],
        risk_reward: Optional[float],
        volume_ratio: float,
        timeframe_directions: dict[str, str],
    ) -> str:
        """진입 품질을 A~F로 구분하되 A/B만 실제 진입을 허용합니다."""
        if signal.startswith("WAIT"):
            return "C" if stop_loss and risk_reward else "D"
        if direction not in ("LONG", "SHORT"):
            return "D"
        if not stop_loss or not risk_reward or risk_reward < 1.1:
            return "F"

        higher_directions = [
            timeframe_directions.get(tf, "HOLD")
            for tf in ("5m", "15m", "30m", "1H", "4H", "6H", "1D")
        ]
        active_higher = [value for value in higher_directions if value in ("LONG", "SHORT")]
        higher_aligned = bool(active_higher) and all(value == direction for value in active_higher)
        if risk_reward >= 2.0 and volume_ratio >= 1.2 and higher_aligned:
            return "A"
        return "B"

    @staticmethod
    def _pricing(price: float, market: dict) -> dict:
        bid = float(market.get("best_bid") or price * 0.99995)
        ask = float(market.get("best_ask") or price * 1.00005)
        mid = (bid + ask) / 2
        return {
            "last_price": round(price, 2),
            "mark_price": round(float(market.get("mark_price") or price), 2),
            "index_price": round(float(market.get("index_price") or market.get("mark_price") or price), 2),
            "best_bid": round(bid, 2),
            "best_ask": round(ask, 2),
            "expected_entry_long": round(ask, 2),
            "expected_entry_short": round(bid, 2),
            "spread_rate": (ask - bid) / mid if mid > 0 else None,
        }

    @staticmethod
    def _risk_prices(
        direction: str,
        entry: float,
        atr: float,
        df=None,
        decision=None,
        last=None,
        timeframe_summaries: Optional[dict[str, dict]] = None,
        risk_settings=None,
    ) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        if direction not in ("LONG", "SHORT") or atr <= 0:
            return None, None, None, None

        timeframe_summaries = timeframe_summaries or {}
        risk_settings = risk_settings or load_risk_settings()
        higher_atrs = [
            float(summary.get("atr14") or 0)
            for tf, summary in timeframe_summaries.items()
            if tf in RISK_TIMEFRAMES and summary.get("data_ready")
        ]
        risk_atr = max([atr, *higher_atrs]) if higher_atrs else atr
        recent = df.tail(STRUCTURE_LOOKBACK) if df is not None and len(df) else None
        support_candidates = [float(recent["low"].min())] if recent is not None and "low" in recent else []
        resistance_candidates = [float(recent["high"].max())] if recent is not None and "high" in recent else []
        for tf in RISK_TIMEFRAMES:
            summary = timeframe_summaries.get(tf) or {}
            support_candidates.append(float(summary.get("recent_support") or 0))
            resistance_candidates.append(float(summary.get("recent_resistance") or 0))
        support_candidates = [value for value in support_candidates if value > 0]
        resistance_candidates = [value for value in resistance_candidates if value > 0]
        recent_support = min(support_candidates) if support_candidates else None
        recent_resistance = max(resistance_candidates) if resistance_candidates else None
        support = getattr(decision, "support_level", None) if decision is not None else None
        breakout = getattr(decision, "breakout_level", None) if decision is not None else None
        ma90 = float(last.get("ma90") or 0) if last is not None else None
        ma200 = float(last.get("ma200") or 0) if last is not None else None
        volume_ratio = float(last.get("volume_ratio") or 0) if last is not None else 0.0

        stop_min = max(1.0, float(risk_settings.stop_gap_min_usdt))
        stop_max = max(stop_min, float(risk_settings.stop_gap_max_usdt))
        tp1_min = max(1.0, float(risk_settings.take_profit_1_min_usdt))
        tp1_max = max(tp1_min, float(risk_settings.take_profit_1_max_usdt))
        tp2_gap = max(tp1_max, float(risk_settings.take_profit_2_usdt))
        base_risk = min(max(risk_atr * RISK_ATR_MULTIPLIER, stop_min), stop_max)
        volume_boost = 0.6 if volume_ratio >= 1.5 else 0.35 if volume_ratio >= 1.2 else 0.15 if volume_ratio >= 1.0 else 0.0
        tp1_r = 0.8 + volume_boost * 0.5
        tp2_r = 1.4 + volume_boost
        buffer = risk_atr * STRUCTURE_STOP_BUFFER_ATR

        if direction == "LONG":
            below_levels = [
                value for value in (support, breakout, ma90, ma200, recent_support)
                if value is not None and value > 0 and value < entry
            ]
            stop = entry - base_risk
            risk = entry - stop
            tp1_gap = min(max(risk, tp1_min), tp1_max)
            tp1 = entry + tp1_gap
            tp2 = entry + tp2_gap
            return (
                stop,
                tp1,
                tp2,
                (tp2 - entry) / risk if risk > 0 else None,
            )

        above_levels = [
            value for value in (support, breakout, ma90, ma200, recent_resistance)
            if value is not None and value > entry
        ]
        stop = entry + base_risk
        risk = stop - entry
        tp1_gap = min(max(risk, tp1_min), tp1_max)
        tp1 = entry - tp1_gap
        tp2 = entry - tp2_gap
        return (
            stop,
            tp1,
            tp2,
            (entry - tp2) / risk if risk > 0 else None,
        )

    @staticmethod
    def _plan_direction(signal: str, direction: str) -> str:
        if direction in ("LONG", "SHORT"):
            return direction
        if signal == "WAIT_RETEST_SHORT":
            return "SHORT"
        if signal == "WAIT_PULLBACK_LONG":
            return "LONG"
        return "HOLD"

    @staticmethod
    def _planned_entry(signal: str, support_level: Optional[float], breakout_level: Optional[float], fallback: float) -> float:
        if signal == "WAIT_RETEST_SHORT" and support_level:
            return float(support_level)
        if signal == "WAIT_PULLBACK_LONG" and breakout_level:
            return float(breakout_level)
        return fallback

    @staticmethod
    def _summary(last, decision, plan_direction: str, planned_entry: float, stop_loss, tp1, tp2) -> dict:
        return {
            "direction": decision.direction,
            "plan_direction": plan_direction,
            "signal": decision.signal,
            "close": float(last.get("close") or 0),
            "ma90": float(last.get("ma90") or 0),
            "ma200": float(last.get("ma200") or 0),
            "rsi14": float(last.get("rsi14") or 0),
            "atr14": float(last.get("atr14") or 0),
            "volume_ratio": float(last.get("volume_ratio") or 0),
            "support_level": decision.support_level,
            "breakout_level": decision.breakout_level,
            "planned_entry": planned_entry,
            "planned_stop_loss": stop_loss,
            "planned_take_profit_1": tp1,
            "planned_take_profit_2": tp2,
        }

    @staticmethod
    def _timeframe_direction(last) -> str:
        ma90 = last.get("ma90")
        ma200 = last.get("ma200")
        close = last.get("close")
        if any(value is None for value in (ma90, ma200, close)):
            return "HOLD"
        ma90 = float(ma90)
        ma200 = float(ma200)
        close = float(close)
        if ma90 <= 0 or ma200 <= 0:
            return "HOLD"
        if close > ma90 > ma200:
            return "LONG"
        if close < ma90 < ma200:
            return "SHORT"
        return "HOLD"

    def _analyze_frames(self, candles_by_timeframe: dict[str, list[dict]]) -> dict:
        directions: dict[str, str] = {}
        summaries: dict[str, dict] = {}
        for tf in TIMEFRAMES:
            candles = candles_by_timeframe.get(tf) or []
            frame = add_indicators(candles)
            if len(frame) < 220:
                directions[tf] = "HOLD"
                summaries[tf] = {"direction": "HOLD", "data_ready": False, "candles": len(frame)}
                continue
            last = frame.iloc[-1]
            direction = self._timeframe_direction(last)
            recent = frame.tail(STRUCTURE_LOOKBACK)
            directions[tf] = direction
            summaries[tf] = {
                "direction": direction,
                "data_ready": True,
                "candles": len(frame),
                "close": float(last.get("close") or 0),
                "ma90": float(last.get("ma90") or 0),
                "ma200": float(last.get("ma200") or 0),
                "rsi14": float(last.get("rsi14") or 0),
                "atr14": float(last.get("atr14") or 0),
                "volume_ratio": float(last.get("volume_ratio") or 0),
                "recent_support": float(recent["low"].min()),
                "recent_resistance": float(recent["high"].max()),
            }
        return {"directions": directions, "summaries": summaries}

    def _timeframe_summary(self, summaries: dict[str, dict], last, decision, plan_direction: str, entry: float, stop_loss, tp1, tp2) -> dict:
        merged = dict(summaries)
        primary = self._summary(last, decision, plan_direction, entry, stop_loss, tp1, tp2)
        for tf in ("1m", "5m"):
            existing = merged.get(tf, {})
            merged[tf] = {**existing, **primary}
        return merged

    @staticmethod
    def _empty(last_price: float, reason: str, frame_info: Optional[dict] = None) -> TradingResult:
        frame_info = frame_info or {"directions": {}, "summaries": {}}
        return TradingResult(
            timestamp=0,
            entry_price=round(last_price, 2),
            direction="HOLD",
            long_probability=50.0,
            short_probability=50.0,
            confidence=0.0,
            stop_loss=None,
            take_profit_1=None,
            take_profit_2=None,
            risk_reward_ratio=None,
            all_time_high_mode=False,
            all_time_low_mode=False,
            timeframe_directions=frame_info["directions"],
            reasons=[reason],
            analysis_price=round(last_price, 2),
            last_price=round(last_price, 2),
            long_score=50.0,
            short_score=50.0,
            entry_grade="F",
            risk_warnings=["데이터 부족"],
            market_mode="HOLD",
            timeframe_summary=frame_info["summaries"],
            strategy_signal="HOLD",
            planned_direction="HOLD",
        )

    def _calc_risk_prices(self, direction: str, entry: float, candles: list[dict]) -> tuple:
        df = add_indicators(candles)
        atr = float(df.iloc[-1].get("atr14") or 0) if len(df) else 0.0
        return self._risk_prices(direction, entry, atr)[:3] + (None,)


__all__ = ["TradingAIEngine", "TradingResult"]
