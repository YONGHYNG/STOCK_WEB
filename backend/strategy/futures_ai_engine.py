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

        # 1. 기본 점수 LONG 50 / SHORT 50에서 시작
        # 2. 5분봉(기준 시간봉)으로 1차 방향 판단
        long_score, short_score, reasons, warnings = self._score_frame(base_df)
        tf_dirs, tf_strengths = self._timeframe_summary(frames)
        # 3. 15분봉/30분봉으로 확인 (일치하면 가점, 충돌하면 중립화)
        long_score, short_score = self._confirm_short_term(long_score, short_score, tf_dirs, reasons, warnings)
        # 4. 1시간봉으로 방향 필터 (같은 방향이면 가점, 반대면 감점)
        long_score, short_score = self._apply_1h_filter(long_score, short_score, tf_dirs, reasons, warnings)
        long_score, short_score = self._adjust_funding(long_score, short_score, market, reasons, warnings)
        # 5. 6시간봉/1일봉은 리스크 필터 — 반대라고 무조건 막지 않고, 둘 다 강하게 반대일 때만 보류
        long_score, short_score = self._apply_long_term_risk_filter(long_score, short_score, tf_dirs, tf_strengths, reasons, warnings)
        long_score, short_score = self._adjust_extremes(
            long_score, short_score, analysis_price, all_time_high, all_time_low, base_df, reasons, warnings
        )

        long_score = max(0.0, min(100.0, long_score))
        short_score = max(0.0, min(100.0, short_score))

        # 6·7. LONG/SHORT 최종 조건 후보: 점수 임계값 + 5m·15m 방향 일치
        candidate = self._candidate_direction(long_score, short_score, tf_dirs)
        pricing = self._pricing(analysis_price, candidate, market)
        self._spread_filter(pricing.get("spread_rate"), warnings)
        self._atr_filter(atr, analysis_price, warnings)

        stop_loss, tp1, tp2, tp3, rr = self._risk_prices(candidate, pricing["entry_price"], atr)
        risk_plan = self._risk_plan(candidate, pricing["entry_price"], stop_loss, tp1, tp2, market, account_equity, warnings)
        # 6·7. 스프레드 정상 + 손익비 1:1.5 이상까지 통과해야 최종 확정, 아니면 8. 그 외는 전부 HOLD
        direction = self._finalize_direction(candidate, pricing.get("spread_rate"), risk_plan.get("net_risk_reward"), warnings)
        if direction != candidate:
            reasons.append(f"{candidate} 후보였지만 스프레드·손익비 조건 미충족으로 HOLD 전환")

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

        # EMA20 vs EMA60: 5분봉 1차 방향(추세) 판단
        trend_strength = abs(ema20 - ema60) / atr if atr > 0 else 0.0
        if trend_strength < 0.3:
            trend = "HOLD"
            reasons.append(f"EMA 간격이 ATR 대비 작아 추세 약함({trend_strength:.2f})으로 봅니다.")
        elif ema20 > ema60:
            trend = "LONG"
            boost = 14 if trend_strength >= 0.8 else 10
            long_score += boost
            short_score -= boost
            reasons.append(f"EMA20>EMA60 상승 추세, 강도 {trend_strength:.2f}: LONG 가점")
        else:
            trend = "SHORT"
            boost = 14 if trend_strength >= 0.8 else 10
            short_score += boost
            long_score -= boost
            reasons.append(f"EMA20<EMA60 하락 추세, 강도 {trend_strength:.2f}: SHORT 가점")

        # RSI는 추세와 같이 판단: 추세와 같은 방향일 때만 가점, 반대면 경고만 남김
        if trend == "LONG":
            if rsi >= 80:
                long_score -= 6
                warnings.append(f"RSI {rsi:.1f}: 상승 추세 중 과열, 추격매수 위험")
            elif rsi >= 50:
                long_score += 6
                reasons.append(f"RSI {rsi:.1f}: 상승 추세와 같은 방향")
            else:
                warnings.append(f"RSI {rsi:.1f}: 상승 추세와 RSI 방향 불일치")
        elif trend == "SHORT":
            if rsi <= 20:
                short_score -= 6
                warnings.append(f"RSI {rsi:.1f}: 하락 추세 중 과매도, 추격매도 위험")
            elif rsi <= 50:
                short_score += 6
                reasons.append(f"RSI {rsi:.1f}: 하락 추세와 같은 방향")
            else:
                warnings.append(f"RSI {rsi:.1f}: 하락 추세와 RSI 방향 불일치")
        else:
            reasons.append(f"추세가 약해 RSI {rsi:.1f}는 참고만 합니다.")

        # MACD 히스토그램 증가/감소
        if macd_delta > 0:
            long_score += 8
            short_score -= 4
            reasons.append("MACD 히스토그램 증가: LONG 가점")
        elif macd_delta < 0:
            short_score += 8
            long_score -= 4
            reasons.append("MACD 히스토그램 감소: SHORT 가점")

        # 거래량 부족은 양쪽 감점, 거래량 급증 + 추세 방향이면 해당 방향만 가점
        if volume_ratio < 0.8:
            long_score -= 4
            short_score -= 4
            warnings.append(f"거래량 비율 {volume_ratio:.2f}: 거래량 부족")
        elif volume_ratio >= 1.8:
            if trend == "LONG":
                long_score += 8
                reasons.append(f"거래량 급증({volume_ratio:.2f}) + 상승 추세: LONG 가점")
            elif trend == "SHORT":
                short_score += 8
                reasons.append(f"거래량 급증({volume_ratio:.2f}) + 하락 추세: SHORT 가점")
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
    def _confirm_short_term(
        long_score: float,
        short_score: float,
        dirs: dict[str, str],
        reasons: list[str],
        warnings: list[str],
    ) -> tuple[float, float]:
        """15분봉/30분봉 확인: 5m·15m·30m이 모두 같으면 강한 가점, 서로 충돌하면 중립 쪽으로 완화."""
        trio = [dirs.get("5m"), dirs.get("15m"), dirs.get("30m")]
        if trio[0] and trio[0] != "HOLD" and trio[0] == trio[1] == trio[2]:
            bonus = 12
            if trio[0] == "LONG":
                long_score += bonus
            else:
                short_score += bonus
            reasons.append(f"5m/15m/30m 방향 일치({trio[0]}): 확인 가점 +{bonus}")
        elif "LONG" in trio and "SHORT" in trio:
            long_score = (long_score + 50.0) / 2
            short_score = (short_score + 50.0) / 2
            warnings.append("5m/15m/30m 방향 충돌: 점수를 중립 쪽으로 완화하여 HOLD 가능성 증가")
        reasons.append(f"단기 시간봉 방향: {dict(zip(['5m', '15m', '30m'], trio))}")
        return long_score, short_score

    @staticmethod
    def _apply_1h_filter(
        long_score: float,
        short_score: float,
        dirs: dict[str, str],
        reasons: list[str],
        warnings: list[str],
    ) -> tuple[float, float]:
        """1시간봉 방향 필터: 같은 방향이면 신뢰도 가점, 반대면 감점."""
        weight = 8
        h1 = dirs.get("1H")
        if h1 == "LONG":
            long_score += weight
            short_score -= weight
            reasons.append("1H 상승과 방향 일치: 신뢰도 가점")
        elif h1 == "SHORT":
            short_score += weight
            long_score -= weight
            reasons.append("1H 하락과 방향 일치: 신뢰도 가점")
        return long_score, short_score

    @staticmethod
    def _apply_long_term_risk_filter(
        long_score: float,
        short_score: float,
        dirs: dict[str, str],
        strengths: dict[str, float],
        reasons: list[str],
        warnings: list[str],
    ) -> tuple[float, float]:
        """6H/1D는 리스크 필터: 반대 방향이라고 무조건 막지 않고, 둘 다 강하게 반대일 때만 진입 보류."""
        provisional = "LONG" if long_score > short_score else "SHORT" if short_score > long_score else "HOLD"
        if provisional == "HOLD":
            return long_score, short_score
        opposite = "SHORT" if provisional == "LONG" else "LONG"
        six_h_opposed = dirs.get("6H") == opposite and strengths.get("6H", 0) >= 0.8
        one_d_opposed = dirs.get("1D") == opposite and strengths.get("1D", 0) >= 0.8
        if six_h_opposed and one_d_opposed:
            warnings.append(f"6H·1D 모두 강한 {opposite} 추세: {provisional} 진입 보류")
            if provisional == "LONG":
                long_score -= 20
            else:
                short_score -= 20
        elif six_h_opposed or one_d_opposed:
            reasons.append("장기 시간봉 중 한쪽만 반대 방향 — 진입을 막지 않고 참고만 함")
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
    def _candidate_direction(long_score: float, short_score: float, dirs: dict[str, str]) -> str:
        """6·7. LONG/SHORT 후보 조건: 점수 임계값 + 5m/15m 방향이 둘 다 같은 쪽이어야 함."""
        long_aligned = dirs.get("5m") == "LONG" and dirs.get("15m") == "LONG"
        short_aligned = dirs.get("5m") == "SHORT" and dirs.get("15m") == "SHORT"
        if long_score >= 65 and short_score <= 35 and long_aligned:
            return "LONG"
        if short_score >= 65 and long_score <= 35 and short_aligned:
            return "SHORT"
        return "HOLD"

    @staticmethod
    def _finalize_direction(
        candidate: str,
        spread: Optional[float],
        net_risk_reward: Optional[float],
        warnings: list[str],
    ) -> str:
        """6·7. 스프레드 정상 + 손익비 1:1.5 이상까지 통과해야 확정. 8. 그 외에는 전부 HOLD."""
        if candidate == "HOLD":
            return "HOLD"
        spread_ok = spread is not None and spread <= SPREAD_NORMAL_RATE
        rr_ok = net_risk_reward is not None and net_risk_reward >= MIN_NET_RISK_REWARD
        if spread_ok and rr_ok:
            return candidate
        if not spread_ok:
            warnings.append("스프레드 기준 미충족으로 최종 HOLD 전환")
        if not rr_ok:
            warnings.append(f"손익비 기준(1:{MIN_NET_RISK_REWARD}) 미충족으로 최종 HOLD 전환")
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
