# 역할: 5분봉 추세·VWAP·RSI 재돌파 기반 BTCUSDT 진입 조건을 판정합니다.
from dataclasses import dataclass
from typing import Optional

import pandas as pd


SIGNAL_TO_DIRECTION = {
    "LONG_RSI_RECLAIM": "LONG",
    "SHORT_RSI_REJECT": "SHORT",
    "LONG_RANGE_REVERSION": "LONG",
    "SHORT_RANGE_REVERSION": "SHORT",
    "LONG_TREND_CONTINUATION": "LONG",
    "SHORT_TREND_CONTINUATION": "SHORT",
    "LONG_BREAKOUT_RETEST": "LONG",
    "SHORT_BREAKOUT_RETEST": "SHORT",
    "LONG_VOLUME_BREAKOUT": "LONG",
    "SHORT_VOLUME_BREAKOUT": "SHORT",
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
RANGE_LONG_RSI_MAX = 42.0
RANGE_SHORT_RSI_MIN = 58.0
TREND_PULLBACK_DISTANCE_ATR_MAX = 0.25
TREND_PULLBACK_VOLUME_RATIO_MIN = 0.70
REGIME_CONFIRMATION_BARS = 3
BREAKOUT_VOLUME_RATIO_MIN = 2.5
BREAKOUT_ADX_MIN = 23.0
BREAKOUT_MAX_DISTANCE_ATR = 1.0
TREND_ADX_MIN = 23.0
TREND_EMA_SLOPE_ATR_MIN = 0.10


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
        self._breakout_level: Optional[float] = None
        self._breakout_age_bars: Optional[int] = None
        self._trend_direction = "HOLD"

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
        regime_candidates = [
            self._classify_regime_row(row)
            for _, row in df.iterrows()
        ]
        self._raw_market_regime = (
            regime_candidates[-1] if regime_candidates else "NEUTRAL"
        )
        self._regime_confirmation_count = 0
        for candidate in reversed(regime_candidates[-REGIME_CONFIRMATION_BARS:]):
            if candidate == self._raw_market_regime:
                self._regime_confirmation_count += 1
            else:
                break
        # 앱 재시작 뒤에도 동일하게 복구되도록 메모리 상태가 아니라 확정봉
        # 이력에서 마지막으로 3개 연속 확인된 장세를 재구성합니다.
        stable_regime = "TREND"
        stable_trend_direction = "HOLD"
        previous_candidate = None
        run_length = 0
        for candidate in regime_candidates:
            if candidate == previous_candidate:
                run_length += 1
            else:
                previous_candidate = candidate
                run_length = 1
            if run_length >= REGIME_CONFIRMATION_BARS:
                if candidate == "RANGE":
                    stable_regime = "RANGE"
                    stable_trend_direction = "HOLD"
                elif candidate in ("TREND_UP", "TREND_DOWN"):
                    stable_regime = "TREND"
                    stable_trend_direction = (
                        "LONG" if candidate == "TREND_UP" else "SHORT"
                    )
        self._market_regime = stable_regime
        self._trend_direction = stable_trend_direction
        raw_stable_regime = (
            "RANGE"
            if self._raw_market_regime == "RANGE"
            else "TREND"
            if self._raw_market_regime in ("TREND_UP", "TREND_DOWN")
            else "NEUTRAL"
        )
        self._regime_transition_pending = (
            raw_stable_regime == "NEUTRAL"
            or raw_stable_regime != self._market_regime
            or (
                self._raw_market_regime == "TREND_UP"
                and self._trend_direction != "LONG"
            )
            or (
                self._raw_market_regime == "TREND_DOWN"
                and self._trend_direction != "SHORT"
            )
        )
        breakout = self._recent_breakout_info(df)
        self._breakout_direction = breakout["direction"]
        self._breakout_level = breakout["level"]
        self._breakout_age_bars = breakout["age_bars"]
        breakout_distance_atr = (
            abs(close - self._breakout_level) / atr
            if self._breakout_level is not None and atr > 0
            else float("inf")
        )
        # RSI 50선 재전환을 기다리는 기존 경로와 별개로, 거래량과 ADX가
        # 동시에 확장되는 첫 돌파봉은 초입에서만 양방향 진입을 허용한다.
        if self._breakout_age_bars == 0:
            long_breakout = (
                self._breakout_direction == "UP"
                and self.last_long_candle != timestamp
                and ema20 > ema50
                and ema_slope > 0
                and close > vwap
            )
            short_breakout = (
                self._breakout_direction == "DOWN"
                and self.last_short_candle != timestamp
                and ema20 < ema50
                and ema_slope < 0
                and close < vwap
            )
            if breakout_distance_atr <= BREAKOUT_MAX_DISTANCE_ATR:
                if long_breakout:
                    return self._decision(
                        "LONG_VOLUME_BREAKOUT",
                        df,
                        [
                            f"상단 거래량 돌파 ${self._breakout_level:,.2f}",
                            f"거래량 비율 {float(last['volume_ratio']):.2f} · ADX {float(last['adx14']):.1f}",
                            "EMA20 > EMA50, 상승 기울기 및 VWAP 상단 확인",
                            f"돌파선 거리 {breakout_distance_atr:.2f} ATR",
                        ],
                        [],
                    )
                if short_breakout:
                    return self._decision(
                        "SHORT_VOLUME_BREAKOUT",
                        df,
                        [
                            f"하단 거래량 돌파 ${self._breakout_level:,.2f}",
                            f"거래량 비율 {float(last['volume_ratio']):.2f} · ADX {float(last['adx14']):.1f}",
                            "EMA20 < EMA50, 하락 기울기 및 VWAP 하단 확인",
                            f"돌파선 거리 {breakout_distance_atr:.2f} ATR",
                        ],
                        [],
                    )
        transition_reason = (
            f"장세 전환 확인 중: {self._raw_market_regime} "
            f"{self._regime_confirmation_count}/{REGIME_CONFIRMATION_BARS} · "
            f"기존 {self._market_regime} 전략 유지"
            if self._regime_transition_pending
            else None
        )
        if self._regime_transition_pending:
            wait_reason = (
                "횡보·추세 조건이 모두 불명확하여 신규 진입 대기"
                if self._raw_market_regime == "NEUTRAL"
                else transition_reason
            )
            return self._decision(
                "HOLD",
                df,
                [wait_reason],
                [],
                self._market_regime,
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

        if self._breakout_direction in ("UP", "DOWN") and self._breakout_age_bars == 0:
            return self._decision(
                "HOLD",
                df,
                [
                    f"{self._breakout_direction} 강한 돌파 직후 추격 진입 금지",
                    (
                        f"돌파선 거리 {breakout_distance_atr:.2f} ATR > "
                        f"{BREAKOUT_MAX_DISTANCE_ATR:.1f} ATR"
                        if breakout_distance_atr > BREAKOUT_MAX_DISTANCE_ATR
                        else "돌파 방향 EMA·VWAP 조건 미충족 · 재테스트 대기"
                    ),
                ],
                [],
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

        # RSI 50선 재돌파가 없더라도 확정 추세에서 EMA20/VWAP 눌림 후
        # 추세 방향으로 다시 마감하면 추가 타점을 제공합니다.
        previous_close = float(prev["close"])
        breakout_retest_volume_ok = (
            float(last["volume_ratio"]) >= TREND_PULLBACK_VOLUME_RATIO_MIN
        )
        if (
            self._trend_direction == "LONG"
            and self._breakout_direction == "UP"
            and self._breakout_level is not None
            and (self._breakout_age_bars or 0) >= 1
            and self.last_long_candle != timestamp
            and float(last["low"]) <= self._breakout_level + atr * 0.20
            and close > self._breakout_level
            and close > previous_close
            and breakout_retest_volume_ok
        ):
            return self._decision(
                "LONG_BREAKOUT_RETEST",
                df,
                [
                    f"상단 돌파가 ${self._breakout_level:,.2f} 재테스트 후 지지",
                    "확정 상승 추세에서 돌파선 위 재마감",
                    f"거래량 비율 {float(last['volume_ratio']):.2f}",
                ],
                [],
            )

        if (
            self._trend_direction == "SHORT"
            and self._breakout_direction == "DOWN"
            and self._breakout_level is not None
            and (self._breakout_age_bars or 0) >= 1
            and self.last_short_candle != timestamp
            and float(last["high"]) >= self._breakout_level - atr * 0.20
            and close < self._breakout_level
            and close < previous_close
            and breakout_retest_volume_ok
        ):
            return self._decision(
                "SHORT_BREAKOUT_RETEST",
                df,
                [
                    f"하단 돌파가 ${self._breakout_level:,.2f} 재테스트 후 저항",
                    "확정 하락 추세에서 돌파선 아래 재마감",
                    f"거래량 비율 {float(last['volume_ratio']):.2f}",
                ],
                [],
            )

        pullback_distance = min(
            abs(float(last["low"]) - ema20),
            abs(float(last["low"]) - vwap),
        )
        long_pullback = (
            self._trend_direction == "LONG"
            and self.last_long_candle != timestamp
            and pullback_distance <= atr * TREND_PULLBACK_DISTANCE_ATR_MAX
            and close > ema20
            and close > vwap
            and close > previous_close
            and float(last["volume_ratio"]) >= TREND_PULLBACK_VOLUME_RATIO_MIN
        )
        if long_pullback:
            return self._decision(
                "LONG_TREND_CONTINUATION",
                df,
                [
                    "확정 상승 추세의 EMA20/VWAP 눌림 확인",
                    f"눌림 거리 {pullback_distance / atr:.2f} ATR",
                    "종가가 EMA20·VWAP 위에서 상승 재개",
                    f"거래량 비율 {float(last['volume_ratio']):.2f}",
                ],
                [],
            )

        short_pullback_distance = min(
            abs(float(last["high"]) - ema20),
            abs(float(last["high"]) - vwap),
        )
        short_pullback = (
            self._trend_direction == "SHORT"
            and self.last_short_candle != timestamp
            and short_pullback_distance <= atr * TREND_PULLBACK_DISTANCE_ATR_MAX
            and close < ema20
            and close < vwap
            and close < previous_close
            and float(last["volume_ratio"]) >= TREND_PULLBACK_VOLUME_RATIO_MIN
        )
        if short_pullback:
            return self._decision(
                "SHORT_TREND_CONTINUATION",
                df,
                [
                    "확정 하락 추세의 EMA20/VWAP 반등 확인",
                    f"반등 거리 {short_pullback_distance / atr:.2f} ATR",
                    "종가가 EMA20·VWAP 아래에서 하락 재개",
                    f"거래량 비율 {float(last['volume_ratio']):.2f}",
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
    def _classify_regime_row(row: pd.Series) -> str:
        required = (
            "adx14", "bb_upper", "bb_mid", "bb_lower", "bb_width",
            "atr14", "ema20", "ema50", "ema20_slope",
        )
        if any(key not in row.index or pd.isna(row.get(key)) for key in required):
            return "NEUTRAL"
        atr = float(row["atr14"])
        if atr <= 0:
            return "NEUTRAL"
        ema20 = float(row["ema20"])
        ema50 = float(row["ema50"])
        ema_slope = float(row["ema20_slope"])
        close = float(row["close"])
        vwap = float(row.get("vwap") or 0)
        adx = float(row["adx14"])
        is_range = (
            atr > 0
            and adx <= RANGE_ADX_MAX
            and abs(ema20 - ema50) / atr <= RANGE_EMA_GAP_ATR_MAX
            and abs(ema_slope) / atr <= RANGE_EMA_SLOPE_ATR_MAX
            and float(row["bb_width"]) <= RANGE_BB_WIDTH_MAX
        )
        if is_range:
            return "RANGE"
        normalized_slope = ema_slope / atr
        if (
            adx >= TREND_ADX_MIN
            and ema20 > ema50
            and normalized_slope >= TREND_EMA_SLOPE_ATR_MIN
            and close > vwap
        ):
            return "TREND_UP"
        if (
            adx >= TREND_ADX_MIN
            and ema20 < ema50
            and normalized_slope <= -TREND_EMA_SLOPE_ATR_MIN
            and close < vwap
        ):
            return "TREND_DOWN"
        return "NEUTRAL"

    @staticmethod
    def _recent_breakout_info(df: pd.DataFrame) -> dict:
        """최근 장세 확인 구간의 강한 돌파 방향·가격·경과 봉을 반환합니다."""
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
                return {
                    "direction": "UP",
                    "level": float(row["bb_upper"]),
                    "age_bars": len(df) - 1 - index,
                }
            if (
                float(row["close"]) < float(row["bb_lower"])
                and float(row["ema20_slope"]) < 0
            ):
                return {
                    "direction": "DOWN",
                    "level": float(row["bb_lower"]),
                    "age_bars": len(df) - 1 - index,
                }
        return {"direction": "HOLD", "level": None, "age_bars": None}

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
            breakout_level=self._breakout_level,
            reasons=decision_reasons,
            warnings=warnings,
            market_regime=market_regime or self._market_regime,
            raw_market_regime=self._raw_market_regime,
            regime_confirmation_count=self._regime_confirmation_count,
            regime_transition_pending=self._regime_transition_pending,
            breakout_direction=self._breakout_direction,
        )


__all__ = ["SIGNAL_TO_DIRECTION", "StrategyDecision", "VolumeTrendRsiStrategy"]
