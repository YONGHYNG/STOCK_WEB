# 역할: 5분봉 추세·VWAP·RSI 재돌파 기반 BTCUSDT 진입 조건을 판정합니다.
from dataclasses import dataclass
from typing import Optional

import pandas as pd


SIGNAL_TO_DIRECTION = {
    "LONG_RSI_RECLAIM": "LONG",
    "SHORT_RSI_REJECT": "SHORT",
}

VOLUME_RATIO_MIN = 0.65
STRUCTURE_WINDOW = 6
RSI_ARM_LOOKBACK = 60
LONG_ARM_RSI = 48.5
SHORT_ARM_RSI = 51.5


@dataclass
class StrategyDecision:
    signal: str
    direction: str
    state: str
    entry_price: float
    support_level: Optional[float]
    breakout_level: Optional[float]
    reasons: list[str]
    warnings: list[str]


class VolumeTrendRsiStrategy:
    """한 RSI 사이클과 한 5분봉에서 방향별 신호를 한 번만 소비합니다."""

    def __init__(self) -> None:
        self.long_armed = False
        self.short_armed = False
        self.last_long_candle: Optional[int] = None
        self.last_short_candle: Optional[int] = None
        self._initialized = False

    def evaluate(self, df: pd.DataFrame) -> StrategyDecision:
        if len(df) < 220:
            return self._decision("HOLD", df, ["MA200 계산을 위한 5분봉 부족"], ["데이터 부족"])

        last = df.iloc[-1]
        prev = df.iloc[-2]
        required = ("ema20", "ema50", "ema20_slope", "ma90", "vwap", "rsi14", "atr14", "volume_ratio")
        if any(pd.isna(last.get(key)) for key in required) or pd.isna(prev.get("rsi14")):
            return self._decision("HOLD", df, ["필수 지표 계산 전"], ["지표 데이터 부족"])

        if not self._initialized:
            history = df["rsi14"].iloc[-RSI_ARM_LOOKBACK:-1].dropna()
            self.long_armed = bool((history <= LONG_ARM_RSI).any())
            self.short_armed = bool((history >= SHORT_ARM_RSI).any())
            self._initialized = True

        rsi = float(last["rsi14"])
        previous_rsi = float(prev["rsi14"])
        if rsi <= LONG_ARM_RSI:
            self.long_armed = True
        if rsi >= SHORT_ARM_RSI:
            self.short_armed = True

        timestamp = int(last.get("timestamp") or len(df) - 1)
        recent = df.iloc[-STRUCTURE_WINDOW:]
        older = df.iloc[-(STRUCTURE_WINDOW * 2):-STRUCTURE_WINDOW]
        rising_structure = (
            float(recent["high"].max()) > float(older["high"].max())
            and float(recent["low"].min()) > float(older["low"].min())
        )
        falling_structure = (
            float(recent["high"].max()) < float(older["high"].max())
            and float(recent["low"].min()) < float(older["low"].min())
        )

        close = float(last["close"])
        ema20 = float(last["ema20"])
        ema50 = float(last["ema50"])
        ema_slope = float(last["ema20_slope"])
        vwap = float(last["vwap"])
        volume_ok = float(last["volume_ratio"]) >= VOLUME_RATIO_MIN
        # 정확히 50선을 한 봉에서 통과할 때만 기다리지 않고,
        # 50선 부근에서 방향을 되돌리는 초기 움직임도 진입 후보로 사용한다.
        long_cross = rsi >= 48.0 and rsi > previous_rsi and previous_rsi <= 52.0
        short_cross = rsi <= 52.0 and rsi < previous_rsi and previous_rsi >= 48.0
        long_structure_ok = rising_structure or (
            close > ema20 and float(last["low"]) >= float(prev["low"])
        )
        short_structure_ok = falling_structure or (
            close < ema20 and float(last["high"]) <= float(prev["high"])
        )

        if (
            self.long_armed
            and self.last_long_candle != timestamp
            and ema20 > ema50
            and ema_slope > 0
            and close > vwap
            and long_cross
        ):
            return self._decision(
                "LONG_RSI_RECLAIM",
                df,
                [
                    "5분봉 상승 구조 확인" if long_structure_ok else "EMA·VWAP 상승 방향 우선",
                    "EMA20 > EMA50, EMA20 기울기 상승",
                    "종가가 VWAP 위",
                    "RSI14가 50선 부근에서 상승 전환",
                    (
                        f"거래량 확인 {float(last['volume_ratio']):.2f}"
                        if volume_ok
                        else f"저거래량 {float(last['volume_ratio']):.2f}, 추세 조건으로 진입"
                    ),
                ],
                [],
            )

        if (
            self.short_armed
            and self.last_short_candle != timestamp
            and ema20 < ema50
            and ema_slope < 0
            and close < vwap
            and short_cross
        ):
            return self._decision(
                "SHORT_RSI_REJECT",
                df,
                [
                    "5분봉 하락 구조 확인" if short_structure_ok else "EMA·VWAP 하락 방향 우선",
                    "EMA20 < EMA50, EMA20 기울기 하락",
                    "종가가 VWAP 아래",
                    "RSI14가 50선 부근에서 하락 전환",
                    (
                        f"거래량 확인 {float(last['volume_ratio']):.2f}"
                        if volume_ok
                        else f"저거래량 {float(last['volume_ratio']):.2f}, 추세 조건으로 진입"
                    ),
                ],
                [],
            )

        return self._decision("HOLD", df, ["5분봉 진입 조건 대기"], [])

    def consume(self, direction: str, timestamp: int) -> None:
        """실제 주문이 생성된 경우에만 해당 RSI 사이클과 5분봉을 소비합니다."""
        if direction == "LONG":
            self.long_armed = False
            self.last_long_candle = int(timestamp)
        elif direction == "SHORT":
            self.short_armed = False
            self.last_short_candle = int(timestamp)

    @staticmethod
    def _decision(signal: str, df: pd.DataFrame, reasons: list[str], warnings: list[str]) -> StrategyDecision:
        close = float(df.iloc[-1]["close"]) if len(df) else 0.0
        return StrategyDecision(
            signal=signal,
            direction=SIGNAL_TO_DIRECTION.get(signal, "HOLD"),
            state="READY" if signal != "HOLD" else "IDLE",
            entry_price=close,
            support_level=None,
            breakout_level=None,
            reasons=reasons,
            warnings=warnings,
        )


__all__ = ["SIGNAL_TO_DIRECTION", "StrategyDecision", "VolumeTrendRsiStrategy"]
