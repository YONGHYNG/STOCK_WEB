# 역할: 매매 조건과 방향 점수를 계산하는 전략 엔진.
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from backend.config import (
    ATR_STOP_MULTIPLIER,
    FUNDING_BLOCK_RATE,
    FUNDING_CAUTION_RATE,
    FUNDING_NORMAL_RATE,
    MIN_NET_RISK_REWARD,
    MIN_TP1_COST_MULTIPLE,
    SLIPPAGE_BUFFER,
    SPREAD_CAUTION_RATE,
    SPREAD_NORMAL_RATE,
    TAKER_FEE_RATE,
    TAKE_PROFIT_1R,
    TAKE_PROFIT_2R,
    TAKE_PROFIT_3R,
)
from backend.indicator.core import add_indicators, to_dataframe


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
    entry_grade: str = "D"
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

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["risk_warnings"] = d.get("risk_warnings") or []
        return d


class TradingAIEngine:
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
        base_tf = "5m" if "5m" in candles_by_timeframe else next(iter(candles_by_timeframe))
        frames = {
            tf: add_indicators(to_dataframe(candles))
            for tf, candles in candles_by_timeframe.items()
            if candles
        }
        base_df = frames.get(base_tf)
        if base_df is None or len(base_df) < 80:
            last_price = float(base_df["close"].iloc[-1]) if base_df is not None and len(base_df) else 0.0
            return self._empty_result(last_price, "분석 가능한 캔들 수가 부족합니다. 최소 80개 이상 필요합니다.")

        market = market or {}
        last = base_df.iloc[-1]
        analysis_price = float(last["close"])
        timestamp = int(last["timestamp"])
        atr = float(last.get("atr14") or 0)

        long_score, short_score, reasons, warnings = self._score_frame(base_df)
        tf_dirs, tf_strengths = self._timeframe_summary(frames)
        long_score, short_score = self._adjust_timeframes(long_score, short_score, tf_dirs, tf_strengths, reasons, warnings)
        long_score, short_score = self._adjust_funding(long_score, short_score, market, reasons, warnings)
        long_score, short_score = self._adjust_extremes(
            long_score, short_score, analysis_price, all_time_high, all_time_low, base_df, reasons, warnings
        )

        long_score = max(0.0, min(100.0, long_score))
        short_score = max(0.0, min(100.0, short_score))
        direction = self._decide_direction(long_score, short_score)
        pricing = self._pricing(analysis_price, direction, market)
        self._spread_filter(pricing.get("spread_rate"), warnings)
        self._atr_filter(atr, analysis_price, warnings)

        stop_loss, tp1, tp2, tp3, rr = self._risk_prices(direction, pricing["entry_price"], atr)
        risk_plan = self._risk_plan(direction, pricing["entry_price"], stop_loss, tp1, tp2, market, account_equity, warnings)
        grade = self._entry_grade(direction, long_score, short_score, tf_dirs, warnings, pricing.get("spread_rate"))
        if grade in ("C", "D", "F"):
            direction = "HOLD"
            reasons.append("진입 등급이 낮거나 위험 필터가 발생하여 신규 진입하지 않습니다.")

        reasons.append(f"분석 기준가=${analysis_price:,.2f}, 예상 진입가=${pricing['entry_price']:,.2f}")
        reasons.append(f"방향 점수 LONG {long_score:.1f} / SHORT {short_score:.1f}, 진입 등급 {grade}")
        for warning in warnings:
            reasons.append(f"위험 경고: {warning}")

        return TradingResult(
            timestamp=timestamp,
            entry_price=round(pricing["entry_price"], 2),
            direction=direction,
            long_probability=round(long_score, 2),
            short_probability=round(short_score, 2),
            confidence=round(abs(long_score - short_score), 2),
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            take_profit_1=round(tp1, 2) if tp1 else None,
            take_profit_2=round(tp2, 2) if tp2 else None,
            risk_reward_ratio=round(rr, 2) if rr else None,
            all_time_high_mode=bool(all_time_high and analysis_price >= all_time_high),
            all_time_low_mode=bool(all_time_low and analysis_price <= all_time_low),
            timeframe_directions=tf_dirs,
            reasons=reasons,
            analysis_price=round(analysis_price, 2),
            last_price=pricing["last_price"],
            mark_price=pricing["mark_price"],
            index_price=pricing["index_price"],
            best_bid=pricing["best_bid"],
            best_ask=pricing["best_ask"],
            expected_entry_long=pricing["expected_entry_long"],
            expected_entry_short=pricing["expected_entry_short"],
            take_profit_3=round(tp3, 2) if tp3 else None,
            long_score=round(long_score, 2),
            short_score=round(short_score, 2),
            entry_grade=grade,
            risk_warnings=warnings,
            spread_rate=pricing["spread_rate"],
            funding_rate=market.get("funding_rate"),
            estimated_fee=risk_plan["estimated_fee"],
            estimated_funding_fee=risk_plan["estimated_funding_fee"],
            net_risk_reward=risk_plan["net_risk_reward"],
            position_size_btc=risk_plan["position_size_btc"],
            position_value=risk_plan["position_value"],
            max_loss_usdt=risk_plan["max_loss_usdt"],
            leverage=risk_plan["leverage"],
            liquidation_price=risk_plan["liquidation_price"],
            liquidation_gap=risk_plan["liquidation_gap"],
            stop_gap=risk_plan["stop_gap"],
        )

    @staticmethod
    def _empty_result(last_price: float, reason: str) -> TradingResult:
        return TradingResult(
            timestamp=0,
            entry_price=last_price,
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
            timeframe_directions={},
            reasons=[reason],
            analysis_price=last_price,
            risk_warnings=[],
        )

    @staticmethod
    def _score_frame(df: pd.DataFrame) -> tuple[float, float, list[str], list[str]]:
        last = df.iloc[-1]
        prev = df.iloc[-2]
        entry = float(last["close"])
        rsi = float(last.get("rsi14") or 50)
        ema20 = float(last.get("ema20") or entry)
        ema60 = float(last.get("ema60") or entry)
        atr = float(last.get("atr14") or 0)
        macd_hist = float(last.get("macd_hist") or 0)
        prev_macd_hist = float(prev.get("macd_hist") or 0)
        macd_delta = macd_hist - prev_macd_hist
        volume = float(last.get("volume") or 0)
        volume_ma20 = float(last.get("volume_ma20") or max(volume, 1))
        volume_ratio = volume / volume_ma20 if volume_ma20 else 1.0
        long_score, short_score = 50.0, 50.0
        reasons: list[str] = []
        warnings: list[str] = []

        trend_strength = abs(ema20 - ema60) / atr if atr > 0 else 0.0
        if trend_strength < 0.3:
            reasons.append(f"EMA 간격이 ATR 대비 작아 추세 약함({trend_strength:.2f})으로 봅니다.")
        elif ema20 > ema60:
            boost = 14 if trend_strength >= 0.8 else 10
            long_score += boost
            short_score -= boost
            reasons.append(f"EMA 상승 추세와 추세 강도 {trend_strength:.2f}를 반영했습니다.")
        else:
            boost = 14 if trend_strength >= 0.8 else 10
            short_score += boost
            long_score -= boost
            reasons.append(f"EMA 하락 추세와 추세 강도 {trend_strength:.2f}를 반영했습니다.")

        if 30 <= rsi < 45:
            long_score += 3
            short_score += 2
        elif 20 <= rsi < 30:
            long_score += 6
            short_score -= 5
        elif rsi < 20:
            long_score += 2
            short_score -= 10
            warnings.append(f"RSI {rsi:.1f}: 투매 및 숏 추격 위험")
        elif 55 < rsi <= 70:
            long_score += 3
            short_score -= 2
        elif 70 < rsi < 80:
            long_score -= 5
            short_score += 4
        elif rsi >= 80:
            long_score -= 12
            short_score += 6
            warnings.append(f"RSI {rsi:.1f}: 추격매수 위험")
        reasons.append(f"RSI {rsi:.1f}를 중립 가산 없이 LONG/SHORT에 반영했습니다.")

        if macd_hist > 0 and macd_delta > 0:
            long_score += 8
            short_score -= 8
            reasons.append("MACD 상승 모멘텀 강화")
        elif macd_hist > 0 and macd_delta < 0:
            long_score += 2
            short_score -= 2
            reasons.append("MACD 상승 모멘텀 둔화")
        elif macd_hist < 0 and macd_delta < 0:
            long_score -= 8
            short_score += 8
            reasons.append("MACD 하락 모멘텀 강화")
        elif macd_hist < 0 and macd_delta > 0:
            long_score -= 2
            short_score += 2
            reasons.append("MACD 하락 모멘텀 둔화")

        high, low = float(last["high"]), float(last["low"])
        open_, close = float(last["open"]), float(last["close"])
        candle_range = max(high - low, 1e-9)
        upper_wick = high - max(open_, close)
        lower_wick = min(open_, close) - low
        if volume_ratio < 0.8:
            long_score -= 4
            short_score -= 4
            warnings.append(f"거래량 비율 {volume_ratio:.2f}: 거래량 부족")
        elif volume_ratio >= 1.8:
            if ema20 > ema60 and macd_delta > 0:
                long_score += 8
            elif ema20 < ema60 and macd_delta < 0:
                short_score += 8
            if upper_wick / candle_range > 0.45:
                long_score -= 6
                warnings.append("거래량 급증 + 긴 윗꼬리: LONG 감점")
            if lower_wick / candle_range > 0.45:
                short_score -= 6
                warnings.append("거래량 급증 + 긴 아랫꼬리: SHORT 감점")
        elif volume_ratio >= 1.2:
            if ema20 > ema60:
                long_score += 4
            elif ema20 < ema60:
                short_score += 4
        reasons.append(f"거래량 비율 {volume_ratio:.2f} 반영")
        return long_score, short_score, reasons, warnings

    @staticmethod
    def _timeframe_summary(frames: dict[str, pd.DataFrame]) -> tuple[dict[str, str], dict[str, float]]:
        directions: dict[str, str] = {}
        strengths: dict[str, float] = {}
        for tf, df in frames.items():
            if len(df) < 80:
                continue
            last, prev = df.iloc[-1], df.iloc[-2]
            entry = float(last["close"])
            ema20 = float(last.get("ema20") or entry)
            ema60 = float(last.get("ema60") or entry)
            atr = float(last.get("atr14") or 0)
            rsi = float(last.get("rsi14") or 50)
            macd = float(last.get("macd_hist") or 0)
            prev_macd = float(prev.get("macd_hist") or 0)
            strength = abs(ema20 - ema60) / atr if atr > 0 else 0.0
            strengths[tf] = strength
            if strength < 0.3:
                directions[tf] = "HOLD"
            elif ema20 > ema60 and (macd >= prev_macd or rsi > 55):
                directions[tf] = "LONG"
            elif ema20 < ema60 and (macd <= prev_macd or rsi < 45):
                directions[tf] = "SHORT"
            else:
                directions[tf] = "HOLD"
        return directions, strengths

    @staticmethod
    def _adjust_timeframes(
        long_score: float,
        short_score: float,
        dirs: dict[str, str],
        strengths: dict[str, float],
        reasons: list[str],
        warnings: list[str],
    ) -> tuple[float, float]:
        for tf, weight in {"1H": 8, "30m": 5, "15m": 4, "5m": 3}.items():
            if dirs.get(tf) == "LONG":
                long_score += weight
                short_score -= weight
            elif dirs.get(tf) == "SHORT":
                short_score += weight
                long_score -= weight
        for tf in ("1D", "6H"):
            if dirs.get(tf) == "SHORT" and strengths.get(tf, 0) >= 0.8:
                long_score -= 18
                warnings.append(f"{tf} 강한 하락: LONG 제한")
            if dirs.get(tf) == "LONG" and strengths.get(tf, 0) >= 0.8:
                short_score -= 18
                warnings.append(f"{tf} 강한 상승: SHORT 제한")
        if ("LONG" in [dirs.get("5m"), dirs.get("15m")] and "SHORT" in [dirs.get("1H"), dirs.get("6H"), dirs.get("1D")]) or (
            "SHORT" in [dirs.get("5m"), dirs.get("15m")] and "LONG" in [dirs.get("1H"), dirs.get("6H"), dirs.get("1D")]
        ):
            warnings.append("상위 시간봉과 하위 시간봉 충돌")
        reasons.append(f"시간봉 방향 필터: {dirs}")
        return long_score, short_score

    @staticmethod
    def _adjust_funding(long_score: float, short_score: float, market: dict, reasons: list[str], warnings: list[str]) -> tuple[float, float]:
        funding = market.get("funding_rate")
        if funding is None:
            warnings.append("펀딩비 데이터 없음")
            return long_score, short_score
        funding = float(funding)
        abs_rate = abs(funding)
        if abs_rate < FUNDING_NORMAL_RATE:
            reasons.append(f"펀딩비 {funding * 100:.4f}% 정상")
        elif abs_rate >= FUNDING_BLOCK_RATE:
            warnings.append(f"펀딩비 {funding * 100:.4f}%: 신규 진입 보류")
        elif abs_rate >= FUNDING_CAUTION_RATE:
            warnings.append(f"펀딩비 {funding * 100:.4f}%: 진입 감점")
        if funding > 0:
            long_score -= 4 if abs_rate >= FUNDING_CAUTION_RATE else 2
        elif funding < 0:
            short_score -= 4 if abs_rate >= FUNDING_CAUTION_RATE else 2
        return long_score, short_score

    @staticmethod
    def _adjust_extremes(
        long_score: float,
        short_score: float,
        price: float,
        ath: Optional[float],
        atl: Optional[float],
        df: pd.DataFrame,
        reasons: list[str],
        warnings: list[str],
    ) -> tuple[float, float]:
        rsi = float(df.iloc[-1].get("rsi14") or 50)
        if ath and price >= ath:
            reasons.append("역사적 신고가: ATR 목표가 사용")
            if rsi >= 80:
                long_score -= 8
                warnings.append("신고가 + RSI 과열")
        if atl and price <= atl:
            reasons.append("역사적 신저가: 지지선보다 리스크 관리 우선")
            long_score -= 8
            short_score -= 4
            warnings.append("신저가 구간")
        return long_score, short_score

    @staticmethod
    def _pricing(analysis_price: float, direction: str, market: dict) -> dict:
        last = float(market.get("last_price") or analysis_price)
        mark = float(market.get("mark_price") or last)
        index = float(market.get("index_price") or mark)
        bid = float(market.get("best_bid") or last * 0.99995)
        ask = float(market.get("best_ask") or last * 1.00005)
        expected_long = ask * (1 + SLIPPAGE_BUFFER)
        expected_short = bid * (1 - SLIPPAGE_BUFFER)
        entry = expected_long if direction == "LONG" else expected_short if direction == "SHORT" else last
        mid = (bid + ask) / 2
        return {
            "last_price": round(last, 2),
            "mark_price": round(mark, 2),
            "index_price": round(index, 2),
            "best_bid": round(bid, 2),
            "best_ask": round(ask, 2),
            "expected_entry_long": round(expected_long, 2),
            "expected_entry_short": round(expected_short, 2),
            "entry_price": entry,
            "spread_rate": (ask - bid) / mid if mid > 0 else None,
        }

    @staticmethod
    def _spread_filter(spread: Optional[float], warnings: list[str]) -> None:
        if spread is None:
            warnings.append("호가 스프레드 데이터 없음")
        elif spread > SPREAD_CAUTION_RATE:
            warnings.append(f"스프레드 {spread * 100:.3f}%: 신규 진입 금지")
        elif spread > SPREAD_NORMAL_RATE:
            warnings.append(f"스프레드 {spread * 100:.3f}%: 진입 주의")

    @staticmethod
    def _atr_filter(atr: float, price: float, warnings: list[str]) -> None:
        if atr <= 0 or price <= 0:
            warnings.append("ATR 데이터 부족")
            return
        atr_rate = atr / price
        if atr_rate > 0.018:
            warnings.append(f"ATR 변동성 {atr_rate * 100:.2f}%: 진입 금지")
        elif atr_rate > 0.012:
            warnings.append(f"ATR 변동성 {atr_rate * 100:.2f}%: 진입 주의")

    @staticmethod
    def _risk_prices(direction: str, entry: float, atr: float) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]]:
        if direction not in ("LONG", "SHORT") or atr <= 0:
            return None, None, None, None, None
        risk = atr * ATR_STOP_MULTIPLIER
        if direction == "LONG":
            return entry - risk, entry + risk * TAKE_PROFIT_1R, entry + risk * TAKE_PROFIT_2R, entry + risk * TAKE_PROFIT_3R, TAKE_PROFIT_1R
        return entry + risk, entry - risk * TAKE_PROFIT_1R, entry - risk * TAKE_PROFIT_2R, entry - risk * TAKE_PROFIT_3R, TAKE_PROFIT_1R

    @staticmethod
    def _risk_plan(
        direction: str,
        entry: float,
        stop: Optional[float],
        tp1: Optional[float],
        tp2: Optional[float],
        market: dict,
        equity: Optional[float],
        warnings: list[str],
    ) -> dict:
        account_equity = float(equity or 1000.0)
        max_loss = account_equity * 0.01
        leverage = 3
        empty = {
            "estimated_fee": None,
            "estimated_funding_fee": None,
            "net_risk_reward": None,
            "position_size_btc": None,
            "position_value": None,
            "max_loss_usdt": round(max_loss, 2),
            "leverage": leverage,
            "liquidation_price": None,
            "liquidation_gap": None,
            "stop_gap": None,
        }
        if direction not in ("LONG", "SHORT") or not stop or not tp1 or not tp2 or entry <= 0:
            return empty
        stop_distance = abs(entry - stop)
        size = max_loss / stop_distance if stop_distance > 0 else 0.0
        value = size * entry
        fee = value * TAKER_FEE_RATE * 2
        funding_fee = value * abs(float(market.get("funding_rate") or 0.0))
        tp1_gross_profit = abs(tp1 - entry) * size
        tp2_gross_profit = abs(tp2 - entry) * size
        net_rr = (tp2_gross_profit - fee - funding_fee) / max_loss if max_loss > 0 else None
        if tp1_gross_profit < (fee + funding_fee) * MIN_TP1_COST_MULTIPLE:
            warnings.append("1차 익절 기대수익 < 총비용 2배")
        if net_rr is not None and net_rr < MIN_NET_RISK_REWARD:
            warnings.append(f"기대 손익비 {net_rr:.2f} < 1.5")
        liq = float(market.get("liquidation_price") or (entry * 0.70 if direction == "LONG" else entry * 1.30))
        liq_gap = abs(entry - liq) / entry
        stop_gap = stop_distance / entry
        if liq_gap <= stop_gap * 1.5:
            warnings.append("청산가와 손절가 거리 부족: 신규 진입 금지")
        elif liq_gap <= stop_gap * 2.0:
            warnings.append("청산가 안전거리 부족: 수량 축소 필요")
        return {
            "estimated_fee": round(fee, 4),
            "estimated_funding_fee": round(funding_fee, 4),
            "net_risk_reward": round(net_rr, 2) if net_rr is not None else None,
            "position_size_btc": round(size, 6),
            "position_value": round(value, 2),
            "max_loss_usdt": round(max_loss, 2),
            "leverage": leverage,
            "liquidation_price": round(liq, 2),
            "liquidation_gap": round(liq_gap, 4),
            "stop_gap": round(stop_gap, 4),
        }

    @staticmethod
    def _decide_direction(long_score: float, short_score: float) -> str:
        if long_score >= 65 and short_score <= 35:
            return "LONG"
        if short_score >= 65 and long_score <= 35:
            return "SHORT"
        return "HOLD"

    @staticmethod
    def _entry_grade(direction: str, long_score: float, short_score: float, dirs: dict[str, str], warnings: list[str], spread: Optional[float]) -> str:
        blocking = ("진입 금지", "진입 보류", "거리 부족", "기대 손익비", "기대수익", "충돌")
        if any(any(key in w for key in blocking) for w in warnings):
            return "F"
        if direction == "HOLD":
            score = max(long_score, short_score)
            return "C" if score >= 55 else "D"
        score = long_score if direction == "LONG" else short_score
        aligned = direction in (dirs.get("1H"), dirs.get("30m")) and direction in (dirs.get("15m"), dirs.get("5m"))
        spread_ok = spread is None or spread <= SPREAD_NORMAL_RATE
        if score >= 75 and aligned and spread_ok:
            return "A"
        if score >= 65:
            return "B"
        if score >= 55:
            return "C"
        return "D"

    def _calc_risk_prices(self, direction: str, entry: float, candles: list[dict]) -> tuple:
        df = add_indicators(to_dataframe(candles))
        atr = float(df.iloc[-1].get("atr14") or 0) if len(df) else 0.0
        return self._risk_prices(direction, entry, atr)[:4]
