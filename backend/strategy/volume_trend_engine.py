# 역할: 5분봉 진입 전략과 1시간봉 ATR 손절·익절을 결합해 API 결과로 변환합니다.
import math
from dataclasses import dataclass
from typing import Optional

from backend.config import SYMBOL, TAKER_FEE_RATE, TIMEFRAMES
from backend.risk.settings import load as load_risk_settings
from backend.strategy.indicator import add_indicators
from backend.strategy.strategy import VolumeTrendRsiStrategy


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
    entry_offset_usdt: Optional[float] = None
    open_interest: Optional[float] = None
    open_interest_change_rate: Optional[float] = None

    def to_dict(self) -> dict:
        data = self.__dict__.copy()
        data["risk_warnings"] = data.get("risk_warnings") or []
        data["warnings"] = data["risk_warnings"]
        data["symbol"] = SYMBOL
        data["timeframe_summary"] = data.get("timeframe_summary") or {}
        return data


class TradingAIEngine:
    def __init__(self) -> None:
        self.strategy = VolumeTrendRsiStrategy()

    def analyze(self, candles: list[dict], **kwargs) -> TradingResult:
        return self.analyze_multi_timeframe({"5m": candles}, **kwargs)

    def consume_signal(self, direction: str, timestamp: int) -> None:
        self.strategy.consume(direction, timestamp)

    def analyze_multi_timeframe(
        self,
        candles_by_timeframe: dict[str, list[dict]],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
        market: Optional[dict] = None,
        account_equity: Optional[float] = None,
    ) -> TradingResult:
        market = market or {}
        frame_info = self._analyze_frames(candles_by_timeframe)
        entry_candles = candles_by_timeframe.get("5m") or []
        # Bitget 최신 항목은 진행 중인 봉이므로 제외하고 확정된 5분봉만 판단한다.
        entry_frame = add_indicators(entry_candles[:-1] if len(entry_candles) > 1 else [])
        if len(entry_frame) < 220:
            price = float(entry_frame.iloc[-1]["close"]) if len(entry_frame) else 0.0
            return self._empty(price, "5분봉 MA200 계산을 위한 확정 캔들이 부족합니다.", frame_info)

        decision = self.strategy.evaluate(entry_frame)
        last = entry_frame.iloc[-1]
        analysis_price = float(market.get("last_price") or last["close"])
        pricing = self._pricing(analysis_price, market)
        direction = decision.direction
        candidate_direction = decision.direction
        warnings = list(decision.warnings)
        reasons = list(decision.reasons)
        settings = load_risk_settings()

        strong_15m = frame_info["directions"].get("15m", "HOLD")
        if direction == "LONG" and strong_15m == "SHORT":
            warnings.append("15분봉 강한 하락 추세로 LONG 진입 차단")
            direction = "HOLD"
        elif direction == "SHORT" and strong_15m == "LONG":
            warnings.append("15분봉 강한 상승 추세로 SHORT 진입 차단")
            direction = "HOLD"

        risk_candles = candles_by_timeframe.get("1H") or []
        risk_frame = add_indicators(risk_candles[:-1] if len(risk_candles) > 1 else [])
        # 단일 시간봉 분석 호환을 위해 1H 데이터가 없을 때만 진입봉 ATR로 대체한다.
        atr = (
            float(risk_frame.iloc[-1].get("atr14") or 0)
            if len(risk_frame)
            else float(last.get("atr14") or 0)
        )
        if not math.isfinite(atr) or atr <= 0:
            atr = float(last.get("atr14") or 0)
        ma90 = float(last.get("ma90") or 0)
        distance_atr = abs(analysis_price - ma90) / atr if atr > 0 else float("inf")
        if direction in ("LONG", "SHORT") and distance_atr > settings.max_ma_distance_atr:
            warnings.append(
                f"가격-MA90 거리 {distance_atr:.2f} ATR > {settings.max_ma_distance_atr:.1f} ATR, 추격 진입 보류"
            )
            direction = "HOLD"

        oi_change = self._optional_float(market.get("open_interest_change_rate"))
        oi_bonus = 0.0
        if direction in ("LONG", "SHORT") and oi_change is not None:
            if oi_change <= -abs(settings.oi_sharp_drop_pct):
                warnings.append(f"OI 급감 {oi_change:.2f}%로 진입 보류")
                direction = "HOLD"
            elif oi_change > 0:
                price_change = float(last["close"]) - float(entry_frame.iloc[-2]["close"])
                if direction == "LONG" and price_change > 0:
                    reasons.append(f"가격 상승과 OI 증가({oi_change:+.2f}%) 확인")
                    oi_bonus = 5.0
                elif direction == "SHORT" and price_change < 0:
                    reasons.append(f"가격 하락과 OI 증가({oi_change:+.2f}%) 확인")
                    oi_bonus = 5.0
        elif oi_change is None:
            reasons.append("OI 데이터 없음: OI 조건만 제외")

        preview_direction = (
            direction
            if direction in ("LONG", "SHORT")
            else candidate_direction
            if candidate_direction in ("LONG", "SHORT")
            else frame_info["directions"].get("5m")
            if frame_info["directions"].get("5m") in ("LONG", "SHORT")
            else "LONG"
            if float(last.get("close") or 0) >= float(last.get("ema20") or 0)
            else "SHORT"
        )
        market_entry = (
            pricing["expected_entry_long"]
            if direction == "LONG"
            else pricing["expected_entry_short"]
            if direction == "SHORT"
            else analysis_price
        )
        entry = market_entry
        entry_atr = float(last.get("atr14") or 0)
        if direction in ("LONG", "SHORT"):
            entry, anchor_name, retest_distance = self._retest_entry(
                direction=direction,
                market_entry=market_entry,
                ema20=float(last.get("ema20") or 0),
                vwap=float(last.get("vwap") or 0),
                atr=entry_atr,
            )
            max_retest_distance = entry_atr * 0.5
            if entry_atr > 0 and retest_distance > max_retest_distance:
                warnings.append(
                    f"{anchor_name} 재테스트 거리 ${retest_distance:,.2f} > "
                    f"5분봉 ATR 0.5배 ${max_retest_distance:,.2f}, 추격 진입 보류"
                )
                direction = "HOLD"
                entry = analysis_price
            elif retest_distance > 0:
                reasons.append(
                    f"{anchor_name} 재테스트 지정가 ${entry:,.2f} "
                    f"(현재 진입가 대비 ${retest_distance:,.2f} 대기)"
                )
        stop, tp1, tp2, rr = self._risk_prices(
            preview_direction, entry, atr, settings.atr_stop_multiplier
        )
        risk_amount = float(account_equity or 100.0) * settings.risk_per_trade_pct / 100
        size = self._position_size(
            risk_amount,
            entry,
            stop,
            market.get("min_trade_num"),
            market.get("size_multiplier"),
        )
        if direction in ("LONG", "SHORT") and size is None:
            warnings.append("0.2% 위험 한도 내 계산 수량이 거래소 최소 주문 수량보다 작아 진입 보류")
            direction = "HOLD"
        value = size * entry if size else None
        fee = value * float(market.get("fee_rate") or TAKER_FEE_RATE) * 2 if value else None

        final_signal = decision.signal if direction in ("LONG", "SHORT") else "HOLD"
        confidence = 100.0 if direction in ("LONG", "SHORT") else 0.0
        long_score = 75.0 + oi_bonus if direction == "LONG" else 25.0 if direction == "SHORT" else 50.0
        short_score = 75.0 + oi_bonus if direction == "SHORT" else 25.0 if direction == "LONG" else 50.0
        reasons += [f"전략 신호: {final_signal}", "5분봉 진입 · 1시간봉 ATR 손절/익절 기준"]
        reasons += [f"경고: {warning}" for warning in warnings]

        summaries = dict(frame_info["summaries"])
        summaries["5m"] = {
            **summaries.get("5m", {}),
            "signal": final_signal,
            "direction": direction,
            "vwap": float(last.get("vwap") or 0),
            "ema20": float(last.get("ema20") or 0),
            "ema50": float(last.get("ema50") or 0),
            "ma_distance_atr": distance_atr,
        }
        return TradingResult(
            timestamp=int(last.get("timestamp") or 0),
            entry_price=round(entry, 2),
            direction=direction,
            long_probability=long_score,
            short_probability=short_score,
            confidence=confidence,
            stop_loss=round(stop, 2) if stop is not None else None,
            take_profit_1=round(tp1, 2) if tp1 is not None else None,
            take_profit_2=round(tp2, 2) if tp2 is not None else None,
            risk_reward_ratio=rr,
            all_time_high_mode=bool(all_time_high and entry >= all_time_high),
            all_time_low_mode=bool(all_time_low and entry <= all_time_low),
            timeframe_directions=frame_info["directions"],
            reasons=reasons,
            analysis_price=round(analysis_price, 2),
            last_price=pricing["last_price"],
            mark_price=pricing["mark_price"],
            index_price=pricing["index_price"],
            best_bid=pricing["best_bid"],
            best_ask=pricing["best_ask"],
            expected_entry_long=pricing["expected_entry_long"],
            expected_entry_short=pricing["expected_entry_short"],
            long_score=long_score,
            short_score=short_score,
            entry_grade="A" if direction in ("LONG", "SHORT") else "F",
            risk_warnings=warnings,
            spread_rate=pricing["spread_rate"],
            funding_rate=self._optional_float(market.get("funding_rate")),
            estimated_fee=round(fee, 4) if fee is not None else None,
            net_risk_reward=rr,
            position_size_btc=size,
            position_value=round(value, 2) if value is not None else None,
            max_loss_usdt=round(risk_amount, 4),
            leverage=int(market.get("leverage") or settings.max_leverage),
            stop_gap=round(abs(entry - stop) / entry, 6) if stop and entry else None,
            market_mode=direction,
            timeframe_summary=summaries,
            strategy_signal=final_signal,
            planned_direction=preview_direction,
            entry_offset_usdt=round(abs(analysis_price - entry), 2),
            open_interest=self._optional_float(market.get("open_interest")),
            open_interest_change_rate=oi_change,
        )

    @staticmethod
    def _risk_prices(direction: str, entry: float, atr: float, multiplier: float = 1.5):
        if direction not in ("LONG", "SHORT") or atr <= 0:
            return None, None, None, None
        risk = atr * multiplier
        if direction == "LONG":
            return entry - risk, entry + risk, entry + risk * 1.5, 1.5
        return entry + risk, entry - risk, entry - risk * 1.5, 1.5

    @staticmethod
    def _position_size(risk_amount, entry, stop, minimum=None, step=None) -> Optional[float]:
        if stop is None:
            return None
        risk_per_btc = abs(float(entry) - float(stop))
        if risk_per_btc <= 0:
            return None
        raw = float(risk_amount) / risk_per_btc
        minimum = max(0.0, float(minimum or 0.001))
        step = max(0.00000001, float(step or 0.001))
        units = int(raw / step)
        normalized = units * step
        if normalized < minimum:
            return None
        decimals = max(0, len(f"{step:.10f}".rstrip("0").split(".")[-1]))
        return round(normalized, decimals)

    @staticmethod
    def _pricing(price: float, market: dict) -> dict:
        bid = float(market.get("best_bid") or price)
        ask = float(market.get("best_ask") or price)
        mid = (bid + ask) / 2
        return {
            "last_price": round(price, 2),
            "mark_price": round(float(market.get("mark_price") or price), 2),
            "index_price": round(float(market.get("index_price") or price), 2),
            "best_bid": round(bid, 2),
            "best_ask": round(ask, 2),
            "expected_entry_long": round(ask, 2),
            "expected_entry_short": round(bid, 2),
            "spread_rate": (ask - bid) / mid if mid > 0 else None,
        }

    @staticmethod
    def _retest_entry(
        direction: str,
        market_entry: float,
        ema20: float,
        vwap: float,
        atr: float,
    ) -> tuple[float, str, float]:
        """현재가를 추격하지 않고 가장 가까운 EMA20/VWAP 재테스트에 지정가를 둡니다."""
        market_entry = float(market_entry or 0)
        indicators = [("EMA20", float(ema20 or 0)), ("VWAP", float(vwap or 0))]
        buffer = max(0.0, float(atr or 0) * 0.075)

        if direction == "LONG":
            supports = [(name, value) for name, value in indicators if 0 < value <= market_entry]
            if not supports:
                return market_entry, "현재가", 0.0
            anchor_name, anchor = max(supports, key=lambda item: item[1])
            entry = min(market_entry, anchor + buffer)
        elif direction == "SHORT":
            resistances = [(name, value) for name, value in indicators if value >= market_entry]
            if not resistances:
                return market_entry, "현재가", 0.0
            anchor_name, anchor = min(resistances, key=lambda item: item[1])
            entry = max(market_entry, anchor - buffer)
        else:
            return market_entry, "현재가", 0.0

        return entry, anchor_name, abs(market_entry - entry)

    @staticmethod
    def _strong_direction(last) -> str:
        close = float(last.get("close") or 0)
        ma90 = float(last.get("ma90") or 0)
        ma200 = float(last.get("ma200") or 0)
        slope = float(last.get("ma90_slope") or 0)
        if close > ma90 > ma200 and slope > 0:
            return "LONG"
        if close < ma90 < ma200 and slope < 0:
            return "SHORT"
        return "HOLD"

    def _analyze_frames(self, candles_by_timeframe: dict[str, list[dict]]) -> dict:
        directions: dict[str, str] = {}
        summaries: dict[str, dict] = {}
        for timeframe in TIMEFRAMES:
            candles = candles_by_timeframe.get(timeframe) or []
            frame = add_indicators(candles[:-1] if len(candles) > 1 else [])
            if len(frame) < 220:
                directions[timeframe] = "HOLD"
                summaries[timeframe] = {"direction": "HOLD", "data_ready": False, "candles": len(frame)}
                continue
            last = frame.iloc[-1]
            direction = self._strong_direction(last)
            directions[timeframe] = direction
            summaries[timeframe] = {
                "direction": direction,
                "data_ready": True,
                "candles": len(frame),
                "close": float(last.get("close") or 0),
                "ma90": float(last.get("ma90") or 0),
                "ma200": float(last.get("ma200") or 0),
                "ma90_slope": float(last.get("ma90_slope") or 0),
                "rsi14": float(last.get("rsi14") or 0),
                "atr14": float(last.get("atr14") or 0),
                "volume_ratio": float(last.get("volume_ratio") or 0),
            }
        return {"directions": directions, "summaries": summaries}

    @staticmethod
    def _optional_float(value) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _empty(price: float, reason: str, frame_info: Optional[dict] = None) -> TradingResult:
        frame_info = frame_info or {"directions": {}, "summaries": {}}
        return TradingResult(
            timestamp=0,
            entry_price=round(price, 2),
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
            analysis_price=round(price, 2),
            last_price=round(price, 2),
            entry_grade="F",
            risk_warnings=["데이터 부족"],
            timeframe_summary=frame_info["summaries"],
        )

    def _calc_risk_prices(self, direction: str, entry: float, candles: list[dict]) -> tuple:
        frame = add_indicators(candles)
        atr = float(frame.iloc[-1].get("atr14") or 0) if len(frame) else 0.0
        return self._risk_prices(direction, entry, atr)


__all__ = ["TradingAIEngine", "TradingResult"]
