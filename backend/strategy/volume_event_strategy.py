"""5분봉 Volume Event 반전/지속 진입 상태 머신.

고정 세션은 분석을 허용하는 시간대일 뿐이며, 이 모듈은 확정봉에서
거래량·ATR 충격이 발생한 뒤 1~3개 반응봉이 반전 또는 추세 지속을
확정했을 때만 LONG/SHORT을 반환한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from backend.strategy.indicator import add_indicators


VOLUME_EVENT_RATIO = 2.0
VOLUME_EVENT_RANGE_ATR = 1.3
EVENT_CONFIRMATION_BARS = 3
RECLAIM_RATIO = 0.40
CONTINUATION_VOLUME_RATIO = 1.0
ATR_STOP_BUFFER = 0.20
MIN_EXPECTED_RR = 1.5


@dataclass
class VolumeEventDecision:
    direction: str = "NO_TRADE"
    state: str = "IDLE"
    market_regime: str = "UNKNOWN"
    strategy_signal: str = "NO_TRADE"
    event_id: Optional[int] = None
    event_type: Optional[str] = None
    event_age_bars: Optional[int] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    reasons: list[str] = field(default_factory=list)

    def to_result(self, base: Optional[dict] = None) -> dict:
        result = dict(base or {})
        public_direction = self.direction if self.direction in ("LONG", "SHORT") else "NO_TRADE"
        result.update({
            "direction": public_direction,
            "planned_direction": public_direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit_1": self.take_profit_1,
            "take_profit_2": self.take_profit_2,
            "risk_reward_ratio": self.risk_reward_ratio,
            "market_mode": self.market_regime,
            "market_regime": self.market_regime,
            "strategy_signal": self.strategy_signal,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_state": self.state,
            "event_age_bars": self.event_age_bars,
            "entry_grade": "A" if public_direction in ("LONG", "SHORT") else "F",
            "confidence": 85.0 if public_direction in ("LONG", "SHORT") else 0.0,
            "reasons": list(self.reasons),
        })
        return result


def _strong_direction(candles: list[dict]) -> str:
    frame = add_indicators(candles)
    if len(frame) < 200:
        return "HOLD"
    row = frame.iloc[-1]
    close = float(row["close"])
    ma90 = float(row["ma90"])
    ma200 = float(row["ma200"])
    slope = float(row["ma90_slope"])
    if close > ma90 > ma200 and slope > 0:
        return "LONG"
    if close < ma90 < ma200 and slope < 0:
        return "SHORT"
    return "HOLD"


def classify_market(frame: pd.DataFrame) -> str:
    """5분봉을 RANGE/TREND_UP/TREND_DOWN/UNKNOWN으로 분류한다."""
    # 지표가 이미 계산된 프레임을 받는다. MA200 계산에 사용된 앞부분은
    # 호출부에서 제거될 수 있으므로 현재 값과 구조 비교용 12봉만 요구한다.
    if len(frame) < 12:
        return "UNKNOWN"
    row = frame.iloc[-1]
    required = ("adx14", "atr14", "ema20", "ema50", "ema20_slope", "ma90", "ma200", "ma90_slope", "vwap", "bb_width")
    if any(pd.isna(row.get(key)) for key in required):
        return "UNKNOWN"
    atr = float(row["atr14"])
    if atr <= 0:
        return "UNKNOWN"
    adx = float(row["adx14"])
    close = float(row["close"])
    ema20 = float(row["ema20"])
    ema50 = float(row["ema50"])
    ema_slope = float(row["ema20_slope"])
    ma90 = float(row["ma90"])
    ma200 = float(row["ma200"])
    ma90_slope = float(row["ma90_slope"])
    vwap = float(row["vwap"])

    recent = frame.iloc[-6:]
    older = frame.iloc[-12:-6]
    higher_structure = (
        float(recent["high"].max()) > float(older["high"].max())
        and float(recent["low"].min()) > float(older["low"].min())
    )
    lower_structure = (
        float(recent["high"].max()) < float(older["high"].max())
        and float(recent["low"].min()) < float(older["low"].min())
    )
    # 각 항목은 시장 상태의 예시 조건이지 모두 동시에 충족해야 하는
    # 절대 조건이 아니다. 점수와 반대 방향 대비 우위를 함께 확인해
    # 이평선 교차 직후처럼 일부 지표가 늦는 구간도 분류하되, 서로
    # 충돌하는 구간은 UNKNOWN으로 남긴다.
    up_score = sum((
        ma90 > ma200,
        ma90_slope > 0,
        ema_slope > 0,
        close > vwap,
        higher_structure,
    ))
    down_score = sum((
        ma90 < ma200,
        ma90_slope < 0,
        ema_slope < 0,
        close < vwap,
        lower_structure,
    ))
    if up_score >= 3 and up_score - down_score >= 2 and (adx >= 18 or higher_structure):
        return "TREND_UP"
    if down_score >= 3 and down_score - up_score >= 2 and (adx >= 18 or lower_structure):
        return "TREND_DOWN"

    flat_shape_score = sum((
        abs(ema20 - ema50) / atr <= 0.60,
        abs(ema_slope) / atr <= 0.12,
        float(row["bb_width"]) <= 0.03,
    ))
    if adx <= 22 and flat_shape_score >= 2 and max(up_score, down_score) <= 3:
        return "RANGE"
    return "UNKNOWN"


def _find_event(frame: pd.DataFrame) -> tuple[Optional[pd.Series], Optional[int], Optional[str]]:
    """현재 확정봉 바로 앞 1~3개 범위에서 가장 최근 Volume Event를 찾는다."""
    current_index = len(frame) - 1
    for age in range(1, EVENT_CONFIRMATION_BARS + 1):
        index = current_index - age
        if index < 20:
            break
        row = frame.iloc[index]
        atr = float(row.get("atr14") or 0)
        volume_ratio = float(row.get("volume_ratio") or 0)
        candle_range = float(row["high"] - row["low"])
        if atr <= 0 or volume_ratio < VOLUME_EVENT_RATIO or candle_range < atr * VOLUME_EVENT_RANGE_ATR:
            continue
        event_type = "DROP_EVENT" if float(row["close"]) < float(row["open"]) else "PUMP_EVENT"
        return row, age, event_type
    return None, None, None


def _auxiliary_directions(candles_15m: list[dict], candles_1h: list[dict]) -> tuple[str, str]:
    return _strong_direction(candles_15m), _strong_direction(candles_1h)


def _regime_allows(regime: str, direction: str, direction_15m: str, direction_1h: str) -> bool:
    if regime == "UNKNOWN":
        return False
    if regime == "TREND_UP" and direction == "SHORT":
        return direction_15m == "SHORT" and direction_1h == "SHORT"
    if regime == "TREND_DOWN" and direction == "LONG":
        return direction_15m == "LONG" and direction_1h == "LONG"
    return True


def _risk_plan(direction: str, entry: float, event: pd.Series, responses: pd.DataFrame) -> tuple:
    atr = float(responses.iloc[-1].get("atr14") or event.get("atr14") or 0)
    if atr <= 0 or entry <= 0:
        return None, None, None, None
    if direction == "LONG":
        structure = min(float(event["low"]), float(responses["low"].min()))
        stop = structure - atr * ATR_STOP_BUFFER
        risk = entry - stop
        tp1, tp2 = entry + risk, entry + risk * 2
    else:
        structure = max(float(event["high"]), float(responses["high"].max()))
        stop = structure + atr * ATR_STOP_BUFFER
        risk = stop - entry
        tp1, tp2 = entry - risk, entry - risk * 2
    if risk <= atr * 0.20 or risk > atr * 3.0:
        return None, None, None, None
    return round(stop, 2), round(tp1, 2), round(tp2, 2), 2.0


class VolumeEventStrategy:
    """Volume Event 하나를 하나의 확정 진입으로 변환한다."""

    def evaluate(
        self,
        candles_5m: list[dict],
        candles_15m: Optional[list[dict]] = None,
        candles_1h: Optional[list[dict]] = None,
    ) -> VolumeEventDecision:
        frame = add_indicators(candles_5m)
        if len(frame) < 220:
            return VolumeEventDecision(state="NO_TRADE", reasons=["지표 계산을 위한 5분봉 부족"])
        # 이벤트 봉 자체를 평균에 넣으면 거래량 배율이 희석된다. 명세대로
        # "직전 20개 확정봉 평균"을 분모로 사용한다.
        prior_volume_mean = frame["volume"].shift(1).rolling(20).mean()
        frame["volume_ratio"] = frame["volume"] / prior_volume_mean.replace(0, 1e-9)
        frame = frame.dropna(subset=["atr14", "adx14", "volume_ratio", "ema20", "vwap"]).reset_index(drop=True)
        if len(frame) < 20:
            return VolumeEventDecision(state="NO_TRADE", reasons=["확정 지표 데이터 부족"])

        regime = classify_market(frame)
        if regime == "UNKNOWN":
            return VolumeEventDecision(
                state="NO_TRADE", market_regime=regime,
                reasons=["시장 상태가 RANGE/TREND로 확정되지 않음"],
            )
        event, age, event_type = _find_event(frame)
        if event is None or age is None or event_type is None:
            return VolumeEventDecision(
                state="IDLE", market_regime=regime,
                reasons=["최근 1~3개 확정봉 내 Volume Event 없음"],
            )

        event_index = len(frame) - 1 - age
        responses = frame.iloc[event_index + 1:]
        current = responses.iloc[-1]
        previous = frame.iloc[-2]
        event_range = float(event["high"] - event["low"])
        event_volume = float(event["volume_ratio"])
        current_volume = float(current["volume_ratio"])
        adx_rising = float(current["adx14"]) > float(previous["adx14"])
        volume_contracting = current_volume < event_volume
        direction_15m, direction_1h = _auxiliary_directions(candles_15m or [], candles_1h or [])

        direction = "NO_TRADE"
        state = "REVERSAL_WAIT"
        signal = "NO_TRADE"
        reasons: list[str] = [
            f"{event_type} 탐지 · 거래량 {event_volume:.2f}배 · 확인 {age}/3봉",
            f"시장 상태 {regime} · 15분 {direction_15m} · 1시간 {direction_1h}",
        ]

        if event_type == "DROP_EVENT":
            reclaim_level = float(event["low"]) + event_range * RECLAIM_RATIO
            recovered = float(current["close"]) >= reclaim_level
            low_defended = (
                float(responses["close"].min()) >= float(event["low"])
                or float(current["close"]) >= float(event["low"]) + event_range * 0.20
            )
            if recovered and low_defended and volume_contracting and float(current["close"]) > float(previous["close"]):
                direction, state, signal = "LONG", "REVERSAL_CONFIRMED", "LONG_VOLUME_MEAN_REVERSION"
                reasons.append(f"급락봉 {RECLAIM_RATIO:.0%} 회복·저점 방어·거래량 감소 확인")
            else:
                lower_structure = (
                    float(current["close"]) < float(event["low"])
                    and float(current["close"]) < float(current["ema20"])
                    and float(current["close"]) < float(current["vwap"])
                    and float(current["high"]) < float(previous["high"])
                    and float(current["low"]) < float(previous["low"])
                    and current_volume >= CONTINUATION_VOLUME_RATIO
                    and adx_rising
                )
                if lower_structure:
                    direction, state, signal = "SHORT", "CONTINUATION_CONFIRMED", "SHORT_VOLUME_CONTINUATION"
                    reasons.append("급락 저점 붕괴·Lower High/Low·ADX 상승 확인")
        else:
            retrace_level = float(event["high"]) - event_range * RECLAIM_RATIO
            reversed_down = float(current["close"]) <= retrace_level
            high_rejected = (
                float(responses["close"].max()) <= float(event["high"])
                or float(current["close"]) <= float(event["high"]) - event_range * 0.20
            )
            if reversed_down and high_rejected and volume_contracting and float(current["close"]) < float(previous["close"]):
                direction, state, signal = "SHORT", "REVERSAL_CONFIRMED", "SHORT_VOLUME_MEAN_REVERSION"
                reasons.append(f"급등봉 {RECLAIM_RATIO:.0%} 되돌림·고점 저항·거래량 감소 확인")
            else:
                higher_structure = (
                    float(current["close"]) > float(event["high"])
                    and float(current["close"]) > float(current["ema20"])
                    and float(current["close"]) > float(current["vwap"])
                    and float(current["high"]) > float(previous["high"])
                    and float(current["low"]) > float(previous["low"])
                    and current_volume >= CONTINUATION_VOLUME_RATIO
                    and adx_rising
                )
                if higher_structure:
                    direction, state, signal = "LONG", "CONTINUATION_CONFIRMED", "LONG_VOLUME_CONTINUATION"
                    reasons.append("급등 고점 돌파·Higher High/Low·ADX 상승 확인")

        event_id = int(event["timestamp"])
        if direction not in ("LONG", "SHORT"):
            if age >= EVENT_CONFIRMATION_BARS:
                state = "NO_TRADE"
                reasons.append("3개 확인봉 내 반전/지속 미확정")
            return VolumeEventDecision(
                state=state, market_regime=regime, event_id=event_id,
                event_type=event_type, event_age_bars=age, reasons=reasons,
            )
        if not _regime_allows(regime, direction, direction_15m, direction_1h):
            reasons.append("기존 추세 반대 진입에 필요한 15분·1시간 전환 미확인")
            return VolumeEventDecision(
                state="NO_TRADE", market_regime=regime, event_id=event_id,
                event_type=event_type, event_age_bars=age, reasons=reasons,
            )

        entry = float(current["close"])
        stop, tp1, tp2, rr = _risk_plan(direction, entry, event, responses)
        if stop is None or rr is None or rr < MIN_EXPECTED_RR:
            reasons.append("구조적 손절 거리 또는 기대 손익비 미충족")
            return VolumeEventDecision(
                state="NO_TRADE", market_regime=regime, event_id=event_id,
                event_type=event_type, event_age_bars=age, reasons=reasons,
            )
        reasons.append(f"구조적 SL ${stop:,.2f} · TP1 1R ${tp1:,.2f} · TP2 2R ${tp2:,.2f}")
        return VolumeEventDecision(
            direction=direction, state=state, market_regime=regime,
            strategy_signal=signal, event_id=event_id, event_type=event_type,
            event_age_bars=age, entry_price=round(entry, 2), stop_loss=stop,
            take_profit_1=tp1, take_profit_2=tp2, risk_reward_ratio=rr,
            reasons=reasons,
        )


__all__ = [
    "VolumeEventDecision", "VolumeEventStrategy", "classify_market",
    "VOLUME_EVENT_RATIO", "VOLUME_EVENT_RANGE_ATR", "EVENT_CONFIRMATION_BARS",
]
