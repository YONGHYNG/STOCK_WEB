from dataclasses import dataclass
from typing import Optional

import pandas as pd

from backend.app.config import ATR_STOP_MULTIPLIER, TAKE_PROFIT_R_MULTIPLIER
from backend.app.indicator import add_indicators, to_dataframe


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

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class TradingAIEngine:
    """
    규칙 기반 초기 분석 엔진.
    - 6년치 데이터는 학습/백테스트/최고가·최저가 기준값 생성에 사용
    - 실시간 판단은 각 시간봉의 최근 캔들만 사용
    - analyze() 내부를 PyTorch/LightGBM/XGBoost inference로 교체 가능
    """

    def analyze(
        self,
        candles: list[dict],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
    ) -> TradingResult:
        return self._analyze_single_timeframe(candles, all_time_high, all_time_low)

    def analyze_multi_timeframe(
        self,
        candles_by_timeframe: dict[str, list[dict]],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
    ) -> TradingResult:
        base_tf = "5m" if "5m" in candles_by_timeframe else next(iter(candles_by_timeframe))
        base_candles = candles_by_timeframe.get(base_tf, [])

        # 기본 타임프레임 지표를 한 번만 계산
        base_df = add_indicators(to_dataframe(base_candles))
        base = self._analyze_with_df(base_df, all_time_high=all_time_high, all_time_low=all_time_low)

        directions: dict[str, str] = {}
        long_adjust = 0.0
        reasons = list(base.reasons)

        for tf, candles in candles_by_timeframe.items():
            if not candles:
                continue
            # base_tf는 이미 계산한 결과 재사용
            if tf == base_tf:
                r_dir = base.direction
            else:
                r_dir = self._analyze_single_timeframe(candles).direction
            directions[tf] = r_dir
            weight = self._timeframe_weight(tf)
            if r_dir == "LONG":
                long_adjust += weight
            elif r_dir == "SHORT":
                long_adjust -= weight

        if directions:
            reasons.append(f"멀티 타임프레임 방향성: {directions}")

        long_prob = max(5.0, min(95.0, base.long_probability + long_adjust))
        short_prob = 100.0 - long_prob

        if long_prob >= 60:
            direction = "LONG"
        elif short_prob >= 60:
            direction = "SHORT"
        else:
            direction = "HOLD"

        # 방향이 상위 시간봉 보정으로 바뀌면 base_df를 재활용해 손절/익절 재계산
        stop_loss = base.stop_loss
        take_profit_1 = base.take_profit_1
        take_profit_2 = base.take_profit_2
        rr = base.risk_reward_ratio
        if direction != base.direction:
            stop_loss, take_profit_1, take_profit_2, rr = self._calc_risk_from_df(
                direction, base.entry_price, base_df
            )
            reasons.append(
                f"기본 {base_tf} 판단은 {base.direction}였으나 상위 시간봉 보정 후 {direction}으로 변경되었습니다."
            )

        return TradingResult(
            timestamp=base.timestamp,
            entry_price=base.entry_price,
            direction=direction,
            long_probability=round(long_prob, 2),
            short_probability=round(short_prob, 2),
            confidence=round(abs(long_prob - short_prob), 2),
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            take_profit_1=round(take_profit_1, 2) if take_profit_1 else None,
            take_profit_2=round(take_profit_2, 2) if take_profit_2 else None,
            risk_reward_ratio=rr,
            all_time_high_mode=base.all_time_high_mode,
            all_time_low_mode=base.all_time_low_mode,
            timeframe_directions=directions,
            reasons=reasons,
        )

    def _analyze_single_timeframe(
        self,
        candles: list[dict],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
    ) -> TradingResult:
        df = add_indicators(to_dataframe(candles))
        return self._analyze_with_df(df, all_time_high=all_time_high, all_time_low=all_time_low)

    def _analyze_with_df(
        self,
        df: pd.DataFrame,
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
    ) -> TradingResult:
        if len(df) < 80:
            last_price = float(df["close"].iloc[-1]) if len(df) else 0.0
            return TradingResult(
                timestamp=int(df["timestamp"].iloc[-1]) if len(df) else 0,
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
                reasons=["분석 가능한 캔들 수가 부족합니다. 최소 80개 이상 필요합니다."],
            )

        last = df.iloc[-1]
        prev = df.iloc[-2]
        entry = float(last["close"])
        rsi = float(last.get("rsi14") or 50)
        ema20 = float(last.get("ema20") or entry)
        ema60 = float(last.get("ema60") or entry)
        macd_hist = float(last.get("macd_hist") or 0)
        prev_macd_hist = float(prev.get("macd_hist") or 0)
        volume = float(last.get("volume") or 0)
        volume_ma20 = float(last.get("volume_ma20") or max(volume, 1))

        long_score = 50.0
        reasons = []

        if ema20 > ema60:
            long_score += 12
            reasons.append("EMA20이 EMA60보다 높아 중기 추세가 우상향입니다.")
        else:
            long_score -= 12
            reasons.append("EMA20이 EMA60보다 낮아 중기 추세가 약합니다.")

        if macd_hist > 0 and macd_hist > prev_macd_hist:
            long_score += 10
            reasons.append("MACD 히스토그램이 양수이고 증가하여 상승 모멘텀이 있습니다.")
        elif macd_hist < 0 and macd_hist < prev_macd_hist:
            long_score -= 10
            reasons.append("MACD 히스토그램이 음수이고 감소하여 하락 모멘텀이 있습니다.")

        if 35 <= rsi <= 65:
            long_score += 6
            reasons.append(f"RSI({rsi:.1f})가 과열이 아닌 중립 구간입니다.")
        elif rsi < 20:
            long_score += 3
            reasons.append(f"RSI({rsi:.1f})가 20 이하로 과매도입니다. 반등 가능성은 있으나 투매 위험도 함께 봅니다.")
        elif rsi < 30:
            long_score += 8
            reasons.append(f"RSI({rsi:.1f})가 과매도 구간에 가까워 반등 가능성이 있습니다.")
        elif rsi >= 80:
            long_score -= 15
            reasons.append(f"RSI({rsi:.1f})가 80 이상으로 추격매수 위험이 큽니다.")
        elif rsi > 70:
            long_score -= 8
            reasons.append(f"RSI({rsi:.1f})가 과열 구간입니다.")

        if volume_ma20 > 0 and volume >= volume_ma20 * 1.5:
            if ema20 > ema60:
                long_score += 6
                reasons.append("거래량이 최근 평균보다 높고 상승 추세가 동반됩니다.")
            else:
                long_score -= 6
                reasons.append("거래량이 급증했지만 하락 추세라 변동성 위험이 큽니다.")

        all_time_high_mode = bool(all_time_high and entry >= all_time_high)
        all_time_low_mode = bool(all_time_low and entry <= all_time_low)

        if all_time_high_mode:
            reasons.append("역사적 신고가 구간입니다. 기존 저항선 대신 ATR 기준 목표가를 사용합니다.")
            if rsi >= 80:
                long_score -= 8
                reasons.append("신고가와 RSI 과열이 겹쳐 되돌림 위험을 추가 반영했습니다.")
            if volume_ma20 > 0 and volume >= volume_ma20 * 2:
                long_score -= 5
                reasons.append("신고가 구간에서 거래량이 20봉 평균의 2배 이상이라 변동성 위험을 반영했습니다.")

        if all_time_low_mode:
            reasons.append("역사적 신저가 구간입니다. 기존 지지선이 무너진 상태로 보고 ATR 기준 목표가/손절가를 사용합니다.")
            if ema20 < ema60:
                long_score -= 10
                reasons.append("신저가와 EMA 역배열이 겹쳐 LONG 역추세 진입 위험을 크게 반영했습니다.")
            if rsi <= 20:
                reasons.append("RSI 20 이하로 과매도 반등 가능성은 있으나, 바닥 예측보다 리스크 관리가 우선입니다.")
            if volume_ma20 > 0 and volume >= volume_ma20 * 2:
                long_score -= 5
                reasons.append("신저가 구간에서 거래량이 20봉 평균의 2배 이상이라 투매/변동성 위험을 반영했습니다.")
            if macd_hist < 0 and macd_hist < prev_macd_hist:
                long_score -= 6
                reasons.append("MACD 하락 모멘텀이 지속되어 추가 하락 위험을 반영했습니다.")

        long_prob = max(5.0, min(95.0, long_score))
        short_prob = 100.0 - long_prob

        if long_prob >= 60:
            direction = "LONG"
        elif short_prob >= 60:
            direction = "SHORT"
        else:
            direction = "HOLD"

        # 이미 계산된 df를 재사용해 손절/익절 계산 (이중 지표 계산 방지)
        stop_loss, take_profit_1, take_profit_2, rr = self._calc_risk_from_df(direction, entry, df)

        return TradingResult(
            timestamp=int(last["timestamp"]),
            entry_price=entry,
            direction=direction,
            long_probability=round(long_prob, 2),
            short_probability=round(short_prob, 2),
            confidence=round(abs(long_prob - short_prob), 2),
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            take_profit_1=round(take_profit_1, 2) if take_profit_1 else None,
            take_profit_2=round(take_profit_2, 2) if take_profit_2 else None,
            risk_reward_ratio=rr,
            all_time_high_mode=all_time_high_mode,
            all_time_low_mode=all_time_low_mode,
            timeframe_directions={},
            reasons=reasons,
        )

    @staticmethod
    def _calc_risk_from_df(
        direction: str, entry: float, df: pd.DataFrame
    ) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        if len(df) == 0:
            return None, None, None, None
        atr = float(df.iloc[-1].get("atr14") or 0)
        if direction == "LONG" and atr > 0:
            risk = atr * ATR_STOP_MULTIPLIER
            return (
                entry - risk,
                entry + risk * TAKE_PROFIT_R_MULTIPLIER,
                entry + risk * 3.0,
                TAKE_PROFIT_R_MULTIPLIER,
            )
        if direction == "SHORT" and atr > 0:
            risk = atr * ATR_STOP_MULTIPLIER
            return (
                entry + risk,
                entry - risk * TAKE_PROFIT_R_MULTIPLIER,
                entry - risk * 3.0,
                TAKE_PROFIT_R_MULTIPLIER,
            )
        return None, None, None, None

    def _calc_risk_prices(
        self, direction: str, entry: float, candles: list[dict]
    ) -> tuple:
        df = add_indicators(to_dataframe(candles))
        return self._calc_risk_from_df(direction, entry, df)

    @staticmethod
    def _timeframe_weight(timeframe: str) -> float:
        return {
            "5m":  2.0,
            "15m": 3.0,
            "30m": 4.0,
            "1H":  5.0,
            "6H":  6.0,
            "1D":  7.0,
            "1W":  5.0,
            "1M":  3.0,
        }.get(timeframe, 1.0)


# Futures engine override.
# Keep this module path stable for the GUI/API while replacing the strategy model.
from backend.app.futures_ai_engine import TradingAIEngine, TradingResult
