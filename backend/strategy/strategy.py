# 역할: 거래량, 추세, RSI 기반 BTCUSDT 선물 전략 조건을 판정합니다.
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


SIGNAL_TO_DIRECTION = {
    "SHORT_REBOUND": "SHORT",
    "SHORT_BREAKDOWN": "SHORT",
    "LONG_BOUNCE": "LONG",
    "LONG_TREND_CHANGE": "LONG",
    "SHORT_TREND_CONTINUATION": "SHORT",
    "LONG_TREND_CONTINUATION": "LONG",
}

BASE_VOLUME_RATIO = 0.5
BREAKOUT_VOLUME_RATIO = 0.8


@dataclass
class StrategyState:
    mode: str = "IDLE"
    support_level: Optional[float] = None
    breakout_level: Optional[float] = None
    wait_started_index: Optional[int] = None
    logs: list[str] = field(default_factory=list)


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
    def __init__(self) -> None:
        self.state = StrategyState()

    def evaluate(self, df: pd.DataFrame) -> StrategyDecision:
        if len(df) < 220:
            return self._decision("HOLD", df, ["MA200 계산을 위한 캔들 데이터 부족"], ["데이터 부족"])
        last = df.iloc[-1]
        prev = df.iloc[-2]
        if pd.isna(last.get("ma90")) or pd.isna(last.get("ma200")) or pd.isna(last.get("rsi14")):
            return self._decision("HOLD", df, ["필수 지표 계산 전"], ["지표 데이터 부족"])

        support_level = float(df["low"].iloc[-21:-1].min())
        reasons: list[str] = []
        warnings: list[str] = []

        if self._short_breakdown_setup(last, support_level):
            self.state.mode = "WAIT_RETEST_SHORT"
            self.state.support_level = support_level
            self.state.wait_started_index = len(df) - 1
            reasons.append(
                f"저점 이탈 감지: close < support {support_level:.2f}, "
                f"volume_ratio >= {BREAKOUT_VOLUME_RATIO:.1f}"
            )
            warnings.append("저점 이탈 직후 시장가 추격 금지, 리테스트 대기")
            return self._decision("WAIT_RETEST_SHORT", df, reasons, warnings, support_level=support_level)

        if self.state.mode == "WAIT_RETEST_SHORT" and self._short_breakdown_entry(last):
            reasons.append("support_level 리테스트 후 종가가 아래에서 마감, RSI < 50")
            signal = self._consume("SHORT_BREAKDOWN")
            return self._decision(signal, df, reasons, warnings, support_level=support_level)

        if self._long_trend_change_setup(last, prev):
            self.state.mode = "WAIT_PULLBACK_LONG"
            self.state.breakout_level = max(float(last["ma90"]), float(last["ma200"]))
            self.state.wait_started_index = len(df) - 1
            reasons.append(
                f"MA90/MA200 상향 돌파 + RSI > 50 + "
                f"volume_ratio >= {BREAKOUT_VOLUME_RATIO:.1f}"
            )
            warnings.append("돌파 직후 시장가 추격 금지, 눌림 대기")
            return self._decision("WAIT_PULLBACK_LONG", df, reasons, warnings, breakout_level=self.state.breakout_level)

        if self.state.mode == "WAIT_PULLBACK_LONG" and self._long_trend_change_entry(last):
            reasons.append("breakout_level 눌림 확인 후 종가 회복, RSI 45~60")
            signal = self._consume("LONG_TREND_CHANGE")
            return self._decision(signal, df, reasons, warnings, support_level=support_level)

        if self._short_rebound(last, prev):
            reasons.append("하락 추세에서 MA90/MA200 반등 실패 + RSI 하락 전환 + 거래량 확인")
            return self._decision("SHORT_REBOUND", df, reasons, warnings, support_level=support_level)

        if self._long_bounce(last, prev, support_level):
            reasons.append("최근 20캔들 저점 지지 + 긴 아래꼬리 + RSI 상승 전환 + 거래량 확인")
            return self._decision("LONG_BOUNCE", df, reasons, warnings, support_level=support_level)

        if self._short_trend_continuation(last):
            reasons.append("하락 추세 지속 + 음봉 확정 + RSI 약세 + 기본 거래량 충족")
            return self._decision("SHORT_TREND_CONTINUATION", df, reasons, warnings, support_level=support_level)

        if self._long_trend_continuation(last):
            reasons.append("상승 추세 지속 + 양봉 확정 + RSI 강세 + 기본 거래량 충족")
            return self._decision("LONG_TREND_CONTINUATION", df, reasons, warnings, support_level=support_level)

        if self.state.mode.startswith("WAIT"):
            reasons.append(f"{self.state.mode} 상태 유지, 확정 캔들 조건 미충족")
            return self._decision(self.state.mode, df, reasons, warnings, support_level=support_level)
        return self._decision("HOLD", df, ["전략 조건 미충족"], warnings, support_level=support_level)

    @staticmethod
    def _near_ma_rejection(last) -> bool:
        ma90 = float(last["ma90"])
        ma200 = float(last["ma200"])
        high = float(last["high"])
        close = float(last["close"])
        touched_ma90 = high >= ma90 and close < ma90
        touched_ma200 = high >= ma200 and close < ma200
        return touched_ma90 or touched_ma200

    def _short_rebound(self, last, prev) -> bool:
        downtrend = float(last["close"]) < float(last["ma90"]) < float(last["ma200"])
        rsi_turn_down = float(prev["rsi14"]) >= 55 and float(last["rsi14"]) < float(prev["rsi14"])
        return bool(
            downtrend
            and self._near_ma_rejection(last)
            and rsi_turn_down
            and float(last["volume_ratio"]) >= BASE_VOLUME_RATIO
        )

    @staticmethod
    def _short_breakdown_setup(last, support_level: float) -> bool:
        return bool(
            float(last["close"]) < support_level
            and float(last["volume_ratio"]) >= BREAKOUT_VOLUME_RATIO
        )

    def _short_breakdown_entry(self, last) -> bool:
        support = self.state.support_level
        if support is None:
            return False
        return bool(float(last["high"]) >= support and float(last["close"]) < support and float(last["rsi14"]) < 50)

    @staticmethod
    def _long_bounce(last, prev, support_level: float) -> bool:
        support_hold = float(last["low"]) <= support_level and float(last["close"]) > support_level
        longer_lower_wick = float(last["lower_wick"]) > float(last["upper_wick"])
        rsi_turn_up = float(prev["rsi14"]) <= 40 and float(last["rsi14"]) > float(prev["rsi14"])
        return bool(
            support_hold
            and longer_lower_wick
            and rsi_turn_up
            and float(last["volume_ratio"]) >= BASE_VOLUME_RATIO
        )

    @staticmethod
    def _long_trend_change_setup(last, prev) -> bool:
        prev_below_ma90 = float(prev["close"]) < float(prev["ma90"])
        current_above_mas = float(last["close"]) > float(last["ma90"]) and float(last["close"]) > float(last["ma200"])
        return bool(
            prev_below_ma90
            and current_above_mas
            and float(last["rsi14"]) > 50
            and float(last["volume_ratio"]) >= BREAKOUT_VOLUME_RATIO
        )

    def _long_trend_change_entry(self, last) -> bool:
        breakout = self.state.breakout_level
        if breakout is None:
            return False
        rsi = float(last["rsi14"])
        return bool(float(last["low"]) <= breakout and float(last["close"]) > breakout and 45 <= rsi <= 60)

    @staticmethod
    def _short_trend_continuation(last) -> bool:
        close = float(last["close"])
        return bool(
            close < float(last["open"])
            and close < float(last["ma90"]) < float(last["ma200"])
            and float(last["rsi14"]) <= 48
            and float(last["volume_ratio"]) >= BASE_VOLUME_RATIO
        )

    @staticmethod
    def _long_trend_continuation(last) -> bool:
        close = float(last["close"])
        return bool(
            close > float(last["open"])
            and close > float(last["ma90"]) > float(last["ma200"])
            and float(last["rsi14"]) >= 52
            and float(last["volume_ratio"]) >= BASE_VOLUME_RATIO
        )

    def _consume(self, signal: str) -> str:
        self.state = StrategyState()
        return signal

    def _decision(
        self,
        signal: str,
        df: pd.DataFrame,
        reasons: list[str],
        warnings: list[str],
        support_level: Optional[float] = None,
        breakout_level: Optional[float] = None,
    ) -> StrategyDecision:
        last_close = float(df.iloc[-1]["close"]) if len(df) else 0.0
        return StrategyDecision(
            signal=signal,
            direction=SIGNAL_TO_DIRECTION.get(signal, "HOLD"),
            state=self.state.mode,
            entry_price=last_close,
            support_level=support_level if support_level is not None else self.state.support_level,
            breakout_level=breakout_level if breakout_level is not None else self.state.breakout_level,
            reasons=reasons,
            warnings=warnings,
        )


__all__ = ["SIGNAL_TO_DIRECTION", "StrategyDecision", "StrategyState", "VolumeTrendRsiStrategy"]
