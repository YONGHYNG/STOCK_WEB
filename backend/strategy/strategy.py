# 역할: 5분봉 추세·VWAP·RSI 재돌파 기반 BTCUSDT 진입 조건을 판정합니다.
from dataclasses import dataclass
from typing import Optional

import pandas as pd


SIGNAL_TO_DIRECTION = {
    "LONG_RSI_RECLAIM": "LONG",
    "SHORT_RSI_REJECT": "SHORT",
    "LONG_RANGE_REVERSION": "LONG",
    "SHORT_RANGE_REVERSION": "SHORT",
}

VOLUME_RATIO_MIN = 0.65
STRUCTURE_WINDOW = 6
RSI_ARM_LOOKBACK = 60
LONG_ARM_RSI = 48.5
SHORT_ARM_RSI = 51.5
RANGE_ADX_MAX = 22.0
RANGE_EMA_GAP_ATR_MAX = 0.60
RANGE_EMA_SLOPE_ATR_MAX = 0.08
RANGE_BB_WIDTH_MAX = 0.03
RANGE_LONG_RSI_MAX = 38.0
RANGE_SHORT_RSI_MIN = 62.0
REGIME_CONFIRMATION_BARS = 3
BREAKOUT_VOLUME_RATIO_MIN = 2.5
BREAKOUT_ADX_MIN = 23.0


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
    market_regime: str = "TREND"
    raw_market_regime: str = "TREND"
    regime_confirmation_count: int = 0
    regime_transition_pending: bool = False
    breakout_direction: str = "HOLD"


class VolumeTrendRsiStrategy:
    """한 RSI 사이클과 한 5분봉에서 방향별 신호를 한 번만 소비합니다."""

    def __init__(self) -> None:
        self.long_armed = False
        self.short_armed = False
        self.last_long_candle: Optional[int] = None
        self.last_short_candle: Optional[int] = None
        self._initialized = False
        self._market_regime = "TREND"
        self._raw_market_regime = "TREND"
        self._regime_confirmation_count = 0
        self._regime_transition_pending = False
        self._breakout_direction = "HOLD"

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
        atr = float(last["atr14"])
        all_range_flags = [
            self._is_range_row(row)
            for _, row in df.iterrows()
        ]
        range_flags = all_range_flags[-REGIME_CONFIRMATION_BARS:]
        raw_is_range = bool(range_flags and range_flags[-1])
        self._raw_market_regime = "RANGE" if raw_is_range else "TREND"
        self._regime_confirmation_count = 0
        for flag in reversed(range_flags):
            if flag == raw_is_range:
                self._regime_confirmation_count += 1
            else:
                break
        # 앱 재시작 뒤에도 동일하게 복구되도록 메모리 상태가 아니라 확정봉
        # 이력에서 마지막으로 3개 연속 확인된 장세를 재구성합니다.
        stable_regime = "TREND"
        previous_flag = None
        run_length = 0
        for flag in all_range_flags:
            if flag == previous_flag:
                run_length += 1
            else:
                previous_flag = flag
                run_length = 1
            if run_length >= REGIME_CONFIRMATION_BARS:
                stable_regime = "RANGE" if flag else "TREND"
        self._market_regime = stable_regime
        self._regime_transition_pending = self._raw_market_regime != self._market_regime
        self._breakout_direction = self._recent_breakout_direction(df)
        transition_reason = (
            f"장세 전환 확인 중: {self._raw_market_regime} "
            f"{self._regime_confirmation_count}/{REGIME_CONFIRMATION_BARS} · "
            f"기존 {self._market_regime} 전략 유지"
            if self._regime_transition_pending
            else None
        )
        is_range = self._market_regime == "RANGE"

        if is_range:
            lower = float(last["bb_lower"])
            mid = float(last["bb_mid"])
            upper = float(last["bb_upper"])
            touched_lower = min(float(prev["low"]), float(last["low"])) <= lower + atr * 0.15
            touched_upper = max(float(prev["high"]), float(last["high"])) >= upper - atr * 0.15

            if (
                self.last_long_candle != timestamp
                and self._breakout_direction != "DOWN"
                and touched_lower
                and previous_rsi <= RANGE_LONG_RSI_MAX
                and rsi > previous_rsi
                and lower < close < mid
            ):
                return self._decision(
                    "LONG_RANGE_REVERSION",
                    df,
                    [
                        f"횡보장 확인: ADX {float(last['adx14']):.1f}",
                        "볼린저밴드 하단 지지 후 밴드 안으로 복귀",
                        f"RSI14 과매도 반등 {previous_rsi:.1f} → {rsi:.1f}",
                        "1차 목표는 볼린저밴드 중앙",
                    ],
                    [],
                    "RANGE",
                )

            if (
                self.last_short_candle != timestamp
                and self._breakout_direction != "UP"
                and touched_upper
                and previous_rsi >= RANGE_SHORT_RSI_MIN
                and rsi < previous_rsi
                and mid < close < upper
            ):
                return self._decision(
                    "SHORT_RANGE_REVERSION",
                    df,
                    [
                        f"횡보장 확인: ADX {float(last['adx14']):.1f}",
                        "볼린저밴드 상단 저항 후 밴드 안으로 복귀",
                        f"RSI14 과매수 하락 {previous_rsi:.1f} → {rsi:.1f}",
                        "1차 목표는 볼린저밴드 중앙",
                    ],
                    [],
                    "RANGE",
                )

            breakout_wait = (
                "상단 강한 돌파 후 횡보 SHORT 진입 차단"
                if self._breakout_direction == "UP"
                else "하단 강한 돌파 후 횡보 LONG 진입 차단"
                if self._breakout_direction == "DOWN"
                else None
            )
            return self._decision(
                "HOLD",
                df,
                [
                    f"횡보장 감지(ADX {float(last['adx14']):.1f}) · 밴드 반전 타점 대기",
                    *([breakout_wait] if breakout_wait else []),
                    *([transition_reason] if transition_reason else []),
                ],
                [],
                "RANGE",
            )

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

        return self._decision(
            "HOLD",
            df,
            ["5분봉 진입 조건 대기", *([transition_reason] if transition_reason else [])],
            [],
        )

    @staticmethod
    def _is_range_row(row: pd.Series) -> bool:
        required = (
            "adx14", "bb_upper", "bb_mid", "bb_lower", "bb_width",
            "atr14", "ema20", "ema50", "ema20_slope",
        )
        if any(key not in row.index or pd.isna(row.get(key)) for key in required):
            return False
        atr = float(row["atr14"])
        return (
            atr > 0
            and float(row["adx14"]) <= RANGE_ADX_MAX
            and abs(float(row["ema20"]) - float(row["ema50"])) / atr
                <= RANGE_EMA_GAP_ATR_MAX
            and abs(float(row["ema20_slope"])) / atr
                <= RANGE_EMA_SLOPE_ATR_MAX
            and float(row["bb_width"]) <= RANGE_BB_WIDTH_MAX
        )

    @staticmethod
    def _recent_breakout_direction(df: pd.DataFrame) -> str:
        """최근 장세 확인 구간의 2.5배 거래량 강한 돌파 방향을 반환합니다."""
        start = max(1, len(df) - REGIME_CONFIRMATION_BARS)
        for index in range(len(df) - 1, start - 1, -1):
            row = df.iloc[index]
            previous = df.iloc[index - 1]
            required = (
                "close", "bb_upper", "bb_lower", "volume_ratio",
                "adx14", "ema20_slope",
            )
            if any(
                key not in row.index
                or pd.isna(row.get(key))
                or key not in previous.index
                or (key == "adx14" and pd.isna(previous.get(key)))
                for key in required
            ):
                continue
            volume_breakout = float(row["volume_ratio"]) >= BREAKOUT_VOLUME_RATIO_MIN
            adx_breakout = (
                float(row["adx14"]) >= BREAKOUT_ADX_MIN
                and float(row["adx14"]) > float(previous["adx14"])
            )
            if not (volume_breakout and adx_breakout):
                continue
            if (
                float(row["close"]) > float(row["bb_upper"])
                and float(row["ema20_slope"]) > 0
            ):
                return "UP"
            if (
                float(row["close"]) < float(row["bb_lower"])
                and float(row["ema20_slope"]) < 0
            ):
                return "DOWN"
        return "HOLD"

    def consume(self, direction: str, timestamp: int) -> None:
        """실제 주문이 생성된 경우에만 해당 RSI 사이클과 5분봉을 소비합니다."""
        if direction == "LONG":
            self.long_armed = False
            self.last_long_candle = int(timestamp)
        elif direction == "SHORT":
            self.short_armed = False
            self.last_short_candle = int(timestamp)

    def _decision(
        self,
        signal: str,
        df: pd.DataFrame,
        reasons: list[str],
        warnings: list[str],
        market_regime: Optional[str] = None,
    ) -> StrategyDecision:
        close = float(df.iloc[-1]["close"]) if len(df) else 0.0
        decision_reasons = list(reasons)
        transition_text = (
            f"장세 전환 확인 중: {self._raw_market_regime} "
            f"{self._regime_confirmation_count}/{REGIME_CONFIRMATION_BARS} · "
            f"기존 {self._market_regime} 전략 유지"
        )
        if (
            self._regime_transition_pending
            and transition_text not in decision_reasons
        ):
            decision_reasons.append(transition_text)
        return StrategyDecision(
            signal=signal,
            direction=SIGNAL_TO_DIRECTION.get(signal, "HOLD"),
            state="READY" if signal != "HOLD" else "IDLE",
            entry_price=close,
            support_level=None,
            breakout_level=None,
            reasons=decision_reasons,
            warnings=warnings,
            market_regime=market_regime or self._market_regime,
            raw_market_regime=self._raw_market_regime,
            regime_confirmation_count=self._regime_confirmation_count,
            regime_transition_pending=self._regime_transition_pending,
            breakout_direction=self._breakout_direction,
        )


__all__ = ["SIGNAL_TO_DIRECTION", "StrategyDecision", "VolumeTrendRsiStrategy"]
