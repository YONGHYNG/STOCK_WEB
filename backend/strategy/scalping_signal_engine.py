# 역할: 선물 단타용 멀티 타임프레임 분석 엔진.
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from backend.config import (
    FUNDING_BLOCK_RATE,
    FUNDING_CAUTION_RATE,
    FUNDING_NORMAL_RATE,
    SPREAD_CAUTION_RATE,
    SPREAD_NORMAL_RATE,
    SYMBOL,
    TAKER_FEE_RATE,
)
from backend.indicator.core import add_indicators, to_dataframe


CORE_TIMEFRAMES = ("5m", "15m", "30m")
REQUIRED_TIMEFRAMES = ("5m", "15m", "30m", "1H", "6H", "1D")
MIN_CANDLES = 80
MAX_ATR_RATIO = 0.018
CAUTION_ATR_RATIO = 0.012
MIN_TREND_RR = 1.5
MIN_REVERSAL_RR = 1.2
ATR_STOP_MULTIPLIER = 1.2


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

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["risk_warnings"] = d.get("risk_warnings") or []
        d["warnings"] = d["risk_warnings"]
        d["timeframe_summary"] = d.get("timeframe_summary") or {}
        d["symbol"] = SYMBOL
        return d


def _num(value, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _cap_grade(grade: str, cap: str) -> str:
    order = {"F": 0, "D": 1, "C": 2, "B": 3, "A": 4}
    return cap if order[grade] > order[cap] else grade


def calculate_indicators(candles: list[dict]) -> pd.DataFrame:
    df = add_indicators(to_dataframe(candles))
    if df.empty:
        return df
    out = df.copy()
    candle_range = (out["high"] - out["low"]).replace(0, 1e-9)
    out["volume_sma20"] = out["volume"].rolling(window=20).mean()
    out["volume_ratio"] = out["volume"] / out["volume_sma20"].replace(0, 1e-9)
    out["upper_wick_ratio"] = (out["high"] - out[["open", "close"]].max(axis=1)) / candle_range
    out["lower_wick_ratio"] = (out[["open", "close"]].min(axis=1) - out["low"]) / candle_range
    out["body_ratio"] = (out["close"] - out["open"]).abs() / candle_range
    out["recent_high"] = out["high"].shift(1).rolling(window=20).max()
    out["recent_low"] = out["low"].shift(1).rolling(window=20).min()
    out["volume_ma20"] = out["volume_sma20"]
    return out


def detect_failed_breakout(frame: dict) -> bool:
    return bool(
        frame.get("broke_recent_high")
        and frame["close"] < frame["recent_high"]
        and frame["upper_wick_ratio"] >= 0.4
        and frame["volume_ratio"] >= 1.8
        and frame["rsi14"] >= 80
    )


def detect_failed_breakdown(frame: dict) -> bool:
    return bool(
        frame.get("broke_recent_low")
        and frame["close"] > frame["recent_low"]
        and frame["lower_wick_ratio"] >= 0.4
        and frame["volume_ratio"] >= 1.8
        and frame["rsi14"] <= 20
    )


def analyze_timeframe(candles: list[dict], timeframe: str) -> dict:
    df = calculate_indicators(candles)
    if len(df) < MIN_CANDLES:
        return {"timeframe": timeframe, "direction": "HOLD", "data_ok": False, "rows": len(df)}
    last = df.iloc[-1]
    prev = df.iloc[-2]
    close = _num(last.get("close"))
    high = _num(last.get("high"))
    low = _num(last.get("low"))
    open_ = _num(last.get("open"))
    atr = _num(last.get("atr14"))
    ema20 = _num(last.get("ema20"), close)
    ema60 = _num(last.get("ema60"), close)
    rsi = _num(last.get("rsi14"), 50.0)
    macd_hist = _num(last.get("macd_hist"))
    prev_macd_hist = _num(prev.get("macd_hist"))
    recent_high = _num(last.get("recent_high"), high)
    recent_low = _num(last.get("recent_low"), low)
    trend_strength = abs(ema20 - ema60) / atr if atr > 0 else 0.0
    direction = "HOLD"
    if ema20 > ema60 and (macd_hist >= prev_macd_hist or macd_hist > 0):
        direction = "LONG"
    elif ema20 < ema60 and (macd_hist <= prev_macd_hist or macd_hist < 0):
        direction = "SHORT"
    frame = {
        "timeframe": timeframe,
        "data_ok": True,
        "rows": len(df),
        "timestamp": int(_num(last.get("timestamp"))),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": _num(last.get("volume")),
        "ema20": ema20,
        "ema60": ema60,
        "rsi14": rsi,
        "macd": _num(last.get("macd")),
        "macd_signal": _num(last.get("macd_signal")),
        "macd_hist": macd_hist,
        "prev_macd_hist": prev_macd_hist,
        "macd_hist_delta": macd_hist - prev_macd_hist,
        "atr14": atr,
        "volume_sma20": _num(last.get("volume_sma20")),
        "volume_ratio": _num(last.get("volume_ratio"), 1.0),
        "upper_wick_ratio": _num(last.get("upper_wick_ratio")),
        "lower_wick_ratio": _num(last.get("lower_wick_ratio")),
        "body_ratio": _num(last.get("body_ratio")),
        "recent_high": recent_high,
        "recent_low": recent_low,
        "broke_recent_high": high > recent_high if recent_high > 0 else False,
        "broke_recent_low": low < recent_low if recent_low > 0 else False,
        "closed_near_high": (high - close) <= (high - low) * 0.25,
        "closed_near_low": (close - low) <= (high - low) * 0.25,
        "is_bullish": close > open_,
        "is_bearish": close < open_,
        "trend_strength": trend_strength,
        "direction": direction,
    }
    frame["failed_breakout"] = detect_failed_breakout(frame)
    frame["failed_breakdown"] = detect_failed_breakdown(frame)
    return frame


def classify_market_mode(frames: dict[str, dict]) -> str:
    f5 = frames.get("5m", {})
    if not all(frames.get(tf, {}).get("data_ok") for tf in CORE_TIMEFRAMES):
        return "HOLD"

    reversal_short = [
        f5["rsi14"] >= 80,
        f5["upper_wick_ratio"] >= 0.4,
        f5["volume_ratio"] >= 1.8,
        f5["failed_breakout"],
        f5["macd_hist_delta"] < 0,
        f5["close"] < f5["ema20"],
        frames["15m"]["macd_hist_delta"] < 0,
        frames["15m"]["rsi14"] >= 75 and frames["15m"]["macd_hist_delta"] < 0,
        f5["broke_recent_high"] and f5["close"] < f5["recent_high"],
    ]
    if sum(bool(x) for x in reversal_short) >= 4:
        return "REVERSAL_SHORT"

    reversal_long = [
        f5["rsi14"] <= 20,
        f5["lower_wick_ratio"] >= 0.4,
        f5["volume_ratio"] >= 1.8,
        f5["failed_breakdown"],
        f5["macd_hist_delta"] > 0,
        f5["close"] > f5["ema20"],
        frames["15m"]["macd_hist_delta"] > 0,
        frames["15m"]["rsi14"] <= 25 and frames["15m"]["macd_hist_delta"] > 0,
        f5["broke_recent_low"] and f5["close"] > f5["recent_low"],
    ]
    if sum(bool(x) for x in reversal_long) >= 4:
        return "REVERSAL_LONG"

    long_emas = sum(frames[tf]["ema20"] > frames[tf]["ema60"] for tf in CORE_TIMEFRAMES)
    short_emas = sum(frames[tf]["ema20"] < frames[tf]["ema60"] for tf in CORE_TIMEFRAMES)
    if (
        long_emas >= 2
        and f5["close"] > f5["ema20"]
        and (f5["macd_hist"] > 0 or f5["macd_hist_delta"] > 0)
        and 45 <= f5["rsi14"] <= 75
        and f5["volume_ratio"] >= 0.8
    ):
        return "TREND_LONG"
    if (
        short_emas >= 2
        and f5["close"] < f5["ema20"]
        and (f5["macd_hist"] < 0 or f5["macd_hist_delta"] < 0)
        and 25 <= f5["rsi14"] <= 55
        and f5["volume_ratio"] >= 0.8
    ):
        return "TREND_SHORT"

    f15 = frames["15m"]
    f30 = frames["30m"]
    ema_gap_small = abs(f5["ema20"] - f5["ema60"]) <= f5["atr14"] * 0.35 if f5["atr14"] > 0 else True
    conflict = f15["direction"] != "HOLD" and f30["direction"] != "HOLD" and f15["direction"] != f30["direction"]
    macd_near_zero = abs(f5["macd_hist"]) <= max(f5["atr14"] * 0.03, f5["close"] * 0.0001)
    rsi_flat = 45 <= f5["rsi14"] <= 55
    low_volume = f5["volume_ratio"] < 1.0
    narrow = (f5["recent_high"] - f5["recent_low"]) / f5["close"] < 0.012 if f5["close"] else False
    return "RANGE" if sum((ema_gap_small, conflict, macd_near_zero, rsi_flat, low_volume, narrow)) >= 4 else "HOLD"


def score_trend_long(frames: dict[str, dict], context: dict) -> None:
    if context["market_mode"] != "TREND_LONG":
        return
    f5 = frames["5m"]
    for tf, points in (("5m", 8), ("15m", 10), ("30m", 8), ("1H", 5)):
        if frames.get(tf, {}).get("ema20", 0) > frames.get(tf, {}).get("ema60", 0):
            context["long_score"] += points
            context["reasons"].append(f"{tf} EMA20>EMA60: LONG +{points}")
    if f5["close"] > f5["ema20"]:
        context["long_score"] += 5
    if f5["macd_hist_delta"] > 0:
        context["long_score"] += 8
    if 45 <= f5["rsi14"] < 60:
        context["long_score"] += 6
    elif 60 <= f5["rsi14"] < 75:
        context["long_score"] += 4
    elif f5["rsi14"] >= 80:
        context["warnings"].append("RSI 과열, LONG 신규진입 보류")
        context["long_score"] -= 10
    elif f5["rsi14"] >= 75:
        context["warnings"].append("LONG 추격매수 주의")
        context["long_score"] -= 5
    if f5["volume_ratio"] >= 1.8 and f5["is_bullish"] and f5["upper_wick_ratio"] < 0.4:
        context["long_score"] += 8
    elif f5["volume_ratio"] >= 1.0:
        context["long_score"] += 5
    context["reasons"].append("상승 추세에서는 RSI 과열을 SHORT 신호가 아닌 LONG 추격 금지로 처리")


def score_trend_short(frames: dict[str, dict], context: dict) -> None:
    if context["market_mode"] != "TREND_SHORT":
        return
    f5 = frames["5m"]
    for tf, points in (("5m", 8), ("15m", 10), ("30m", 8), ("1H", 5)):
        if frames.get(tf, {}).get("ema20", 0) < frames.get(tf, {}).get("ema60", 0):
            context["short_score"] += points
            context["reasons"].append(f"{tf} EMA20<EMA60: SHORT +{points}")
    if f5["close"] < f5["ema20"]:
        context["short_score"] += 5
    if f5["macd_hist_delta"] < 0:
        context["short_score"] += 8
    if 40 <= f5["rsi14"] <= 55:
        context["short_score"] += 6
    elif 25 < f5["rsi14"] < 40:
        context["short_score"] += 4
    elif f5["rsi14"] <= 20:
        context["warnings"].append("RSI 과매도, SHORT 신규진입 보류")
        context["short_score"] -= 10
    elif f5["rsi14"] <= 25:
        context["warnings"].append("SHORT 추격매도 주의")
        context["short_score"] -= 5
    if f5["volume_ratio"] >= 1.8 and f5["is_bearish"] and f5["lower_wick_ratio"] < 0.4:
        context["short_score"] += 8
    elif f5["volume_ratio"] >= 1.0:
        context["short_score"] += 5
    context["reasons"].append("하락 추세에서는 RSI 과매도를 LONG 신호가 아닌 SHORT 추격 금지로 처리")


def score_reversal_short(frames: dict[str, dict], context: dict) -> None:
    if context["market_mode"] != "REVERSAL_SHORT":
        return
    context["short_score"] += 25
    context["long_score"] -= 15
    context["grade_cap"] = _cap_grade(context["grade_cap"], "B")
    context["position_size_ratio"] = min(context["position_size_ratio"], 0.5)
    context["warnings"].append("상승 과열 후 실패 신호, 역추세 SHORT 후보")
    context["reasons"].append("REVERSAL_SHORT는 최대 B등급, 수량 50% 제한")


def score_reversal_long(frames: dict[str, dict], context: dict) -> None:
    if context["market_mode"] != "REVERSAL_LONG":
        return
    context["long_score"] += 25
    context["short_score"] -= 15
    context["grade_cap"] = _cap_grade(context["grade_cap"], "B")
    context["position_size_ratio"] = min(context["position_size_ratio"], 0.5)
    context["warnings"].append("하락 과열 후 회복 신호, 역추세 LONG 후보")
    context["reasons"].append("REVERSAL_LONG은 최대 B등급, 수량 50% 제한")


def apply_funding_filter(score: dict, funding_rate: Optional[float]) -> dict:
    if funding_rate is None:
        score["warnings"].append("펀딩비 데이터 없음")
        return score
    funding = float(funding_rate)
    abs_rate = abs(funding)
    if funding > 0:
        if abs_rate >= FUNDING_BLOCK_RATE:
            score["long_score"] -= 10
            score["warnings"].append("롱 포지션 과밀")
        elif abs_rate >= FUNDING_CAUTION_RATE:
            score["long_score"] -= 6
        elif abs_rate >= FUNDING_NORMAL_RATE:
            score["long_score"] -= 2
    elif funding < 0:
        if abs_rate >= FUNDING_BLOCK_RATE:
            score["short_score"] -= 10
            score["warnings"].append("숏 포지션 과밀")
        elif abs_rate >= FUNDING_CAUTION_RATE:
            score["short_score"] -= 6
        elif abs_rate >= FUNDING_NORMAL_RATE:
            score["short_score"] -= 2
    score["reasons"].append(f"펀딩비 {funding * 100:.4f}% 반영")
    return score


def apply_volume_filter(score: dict, frame: dict) -> dict:
    vr = frame.get("volume_ratio", 1.0)
    if vr < 0.7:
        score["long_score"] -= 5
        score["short_score"] -= 5
        score["warnings"].append("거래량 부족")
        score["grade_cap"] = _cap_grade(score["grade_cap"], "C")
    if vr >= 1.8 and frame.get("is_bullish") and frame.get("upper_wick_ratio", 0) >= 0.4:
        score["long_score"] -= 5
        score["warnings"].append("거래량 급증 + 윗꼬리, 상승 실패 가능성")
    if vr >= 1.8 and frame.get("is_bearish") and frame.get("lower_wick_ratio", 0) >= 0.4:
        score["short_score"] -= 5
        score["warnings"].append("거래량 급증 + 아랫꼬리, 하락 실패 가능성")
    return score


def apply_timeframe_filter(score: dict, frames: dict[str, dict]) -> dict:
    direction = "LONG" if score["long_score"] > score["short_score"] else "SHORT" if score["short_score"] > score["long_score"] else "HOLD"
    if direction == "HOLD":
        return score
    aligned = sum(frames.get(tf, {}).get("direction") == direction for tf in CORE_TIMEFRAMES)
    opposite = "SHORT" if direction == "LONG" else "LONG"
    if aligned >= 2:
        score["reasons"].append(f"5m/15m/30m 중 {aligned}개 {direction} 정렬")
    if frames.get("1H", {}).get("direction") == direction:
        score[f"{direction.lower()}_score"] += 5
    if frames.get("6H", {}).get("direction") == opposite:
        score[f"{direction.lower()}_score"] -= 3
        score["warnings"].append(f"6H가 {direction} 반대 방향")
    if frames.get("1D", {}).get("direction") == opposite:
        score[f"{direction.lower()}_score"] -= 2
        score["warnings"].append(f"1D가 {direction} 반대 방향")
    if frames.get("6H", {}).get("direction") == opposite and frames.get("1D", {}).get("direction") == opposite:
        score["grade_cap"] = _cap_grade(score["grade_cap"], "B")
        score["warnings"].append("6H와 1D가 모두 진입 방향과 반대")
    if (
        frames.get("6H", {}).get("direction") == opposite
        and frames.get("6H", {}).get("trend_strength", 0) >= 0.8
        and frames.get("1D", {}).get("direction") == opposite
        and frames.get("1D", {}).get("trend_strength", 0) >= 0.8
    ):
        score["position_size_ratio"] = min(score["position_size_ratio"], 0.5)
        score["warnings"].append("6H와 1D가 모두 강한 반대 추세, 수량 50% 제한")
    return score


def _pricing(price: float, market: dict) -> dict:
    last = float(market.get("last_price") or market.get("current_price") or price)
    bid = float(market.get("best_bid") or market.get("bid") or last * 0.99995)
    ask = float(market.get("best_ask") or market.get("ask") or last * 1.00005)
    mid = (bid + ask) / 2 if bid > 0 and ask > 0 else last
    raw_spread = market.get("spread")
    spread_rate = float(raw_spread) / mid if raw_spread is not None and float(raw_spread) > 0.01 and mid > 0 else (ask - bid) / mid
    return {
        "last_price": round(last, 2),
        "mark_price": round(float(market.get("mark_price") or last), 2),
        "index_price": round(float(market.get("index_price") or market.get("mark_price") or last), 2),
        "best_bid": round(bid, 2),
        "best_ask": round(ask, 2),
        "expected_entry_long": round(ask * 1.0003, 2),
        "expected_entry_short": round(bid * 0.9997, 2),
        "spread_rate": spread_rate,
    }


def calculate_stop_loss_take_profit(result: dict, context: dict) -> dict:
    direction = result["direction"]
    f5 = context["frames"]["5m"]
    if direction not in ("LONG", "SHORT"):
        result.update({"stop_loss": None, "take_profit_1": None, "take_profit_2": None, "risk_reward_ratio": None})
        return result
    entry = result["entry_price"]
    atr = f5["atr14"]
    if atr <= 0:
        context["risk_blocker"] = True
        context["warnings"].append("ATR 데이터 부족")
        return result
    if direction == "LONG":
        stop = min(f5["recent_low"], entry - atr * ATR_STOP_MULTIPLIER)
        risk = entry - stop
        tp1 = entry + risk
        tp2 = entry + risk * (1.2 if context["market_mode"] == "REVERSAL_LONG" else 1.5)
    else:
        stop = max(f5["recent_high"], entry + atr * ATR_STOP_MULTIPLIER)
        risk = stop - entry
        tp1 = entry - risk
        tp2 = entry - risk * (1.2 if context["market_mode"] == "REVERSAL_SHORT" else 1.5)
    result.update(
        {
            "stop_loss": stop,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "take_profit_3": None,
            "risk_reward_ratio": abs(tp2 - entry) / risk if risk > 0 else 0,
            "stop_gap": risk / entry if entry > 0 else None,
        }
    )
    return result


def apply_risk_filter(result: dict, context: dict) -> dict:
    warnings = context["warnings"]
    f5 = context["frames"].get("5m", {})
    spread = result.get("spread_rate")
    if spread is None:
        warnings.append("호가 스프레드 데이터 없음")
    elif spread >= SPREAD_CAUTION_RATE:
        context["risk_blocker"] = True
        warnings.append("스프레드 과도")
    elif spread > SPREAD_NORMAL_RATE:
        context["grade_cap"] = _cap_grade(context["grade_cap"], "C")
        warnings.append("스프레드 다소 넓음")
    atr_ratio = f5.get("atr14", 0) / result["entry_price"] if result["entry_price"] > 0 else 0
    if atr_ratio >= MAX_ATR_RATIO:
        context["risk_blocker"] = True
        warnings.append("ATR 변동성 과도")
    elif atr_ratio >= CAUTION_ATR_RATIO:
        context["grade_cap"] = _cap_grade(context["grade_cap"], "C")
        warnings.append("ATR 변동성 확대")
    min_rr = MIN_REVERSAL_RR if context["market_mode"].startswith("REVERSAL") else MIN_TREND_RR
    rr = result.get("risk_reward_ratio")
    if result["direction"] in ("LONG", "SHORT") and (rr is None or rr < min_rr):
        context["risk_blocker"] = True
        warnings.append(f"손익비 부족: 1:{rr:.2f}" if rr else "손익비 부족")
    liq = context["market"].get("liquidation_price")
    if result["direction"] in ("LONG", "SHORT") and liq:
        liq_gap = abs(result["entry_price"] - float(liq)) / result["entry_price"]
        result["liquidation_price"] = float(liq)
        result["liquidation_gap"] = liq_gap
        if result.get("stop_gap") and liq_gap <= result["stop_gap"] * 1.5:
            context["risk_blocker"] = True
            warnings.append("청산가와 현재가 거리 부족")
    if context["data_insufficient"]:
        context["risk_blocker"] = True
        warnings.append("캔들 데이터 부족")
    if f5.get("volume_sma20", 0) <= 0:
        context["risk_blocker"] = True
        warnings.append("거래량 데이터 부족")
    if (
        context["frames"].get("5m", {}).get("direction") != "HOLD"
        and context["frames"].get("15m", {}).get("direction") not in ("HOLD", context["frames"].get("5m", {}).get("direction"))
        and context["frames"].get("30m", {}).get("direction") == "HOLD"
    ):
        context["risk_blocker"] = True
        warnings.append("5m와 15m 방향이 완전히 반대이고 30m도 애매함")
    if context["long_score"] >= 60 and context["short_score"] >= 60:
        context["risk_blocker"] = True
        warnings.append("LONG / SHORT 점수 충돌")
    return result


def decide_final_direction(result: dict) -> dict:
    if result.get("risk_blocker") or result["market_mode"] == "RANGE":
        result["direction"] = "HOLD"
    elif result["long_score"] >= 65 and result["short_score"] <= 40 and result["market_mode"] in ("TREND_LONG", "REVERSAL_LONG"):
        result["direction"] = "LONG"
    elif result["short_score"] >= 65 and result["long_score"] <= 40 and result["market_mode"] in ("TREND_SHORT", "REVERSAL_SHORT"):
        result["direction"] = "SHORT"
    else:
        result["direction"] = "HOLD"
    return result


def calculate_entry_grade(result: dict, context: dict) -> dict:
    direction = result["direction"]
    mode = result["market_mode"]
    if direction not in ("LONG", "SHORT") or context["risk_blocker"] or mode in ("RANGE", "HOLD"):
        result["entry_grade"] = "F" if context["risk_blocker"] or mode == "RANGE" else "D"
        return result
    score = result["long_score"] if direction == "LONG" else result["short_score"]
    aligned_core = sum(context["frames"].get(tf, {}).get("direction") == direction for tf in CORE_TIMEFRAMES)
    h1_match = context["frames"].get("1H", {}).get("direction") == direction
    rr = result.get("risk_reward_ratio") or 0
    rsi = context["frames"]["5m"]["rsi14"]
    overheat = (direction == "LONG" and rsi >= 75) or (direction == "SHORT" and rsi <= 25)
    major_warning = any(key in w for w in context["warnings"] for key in ("과도", "부족", "충돌", "보류", "거리 부족"))
    if mode in ("TREND_LONG", "TREND_SHORT") and score >= 80 and aligned_core == 3 and h1_match and not overheat and rr >= MIN_TREND_RR and not major_warning:
        grade = "A"
    elif score >= 70 and aligned_core >= 2 and rr >= 1.3 and not major_warning:
        grade = "B"
    elif score >= 60:
        grade = "C"
    else:
        grade = "D"
    if overheat:
        grade = _cap_grade(grade, "B")
    result["entry_grade"] = _cap_grade(grade, context["grade_cap"])
    if result["entry_grade"] in ("C", "D", "F"):
        result["direction"] = "HOLD"
        context["reasons"].append(f"진입 등급 {result['entry_grade']}이므로 자동진입하지 않음")
    return result


def analyze_scalping_signal(input_data: dict) -> dict:
    candles_by_timeframe = input_data.get("candles_by_timeframe") or input_data.get("candles") or {}
    market = input_data.get("market") or {}
    frames = {tf: analyze_timeframe(candles_by_timeframe.get(tf, []), tf) for tf in REQUIRED_TIMEFRAMES}
    data_insufficient = any(not frames[tf].get("data_ok") for tf in CORE_TIMEFRAMES)
    market_mode = classify_market_mode(frames)
    context = {
        "symbol": input_data.get("symbol", SYMBOL),
        "market": market,
        "frames": frames,
        "market_mode": market_mode,
        "long_score": 50.0,
        "short_score": 50.0,
        "warnings": [],
        "reasons": [f"시장 모드: {market_mode}"],
        "risk_blocker": data_insufficient,
        "grade_cap": "A",
        "position_size_ratio": 1.0,
        "data_insufficient": data_insufficient,
    }
    if data_insufficient:
        context["warnings"].append("데이터 부족으로 HOLD")
    if market_mode == "RANGE":
        context["warnings"].append("횡보장: 별도 박스권 전략 없음, HOLD")
    score_trend_long(frames, context)
    score_trend_short(frames, context)
    score_reversal_short(frames, context)
    score_reversal_long(frames, context)
    apply_funding_filter(context, market.get("funding_rate"))
    if frames.get("5m", {}).get("data_ok"):
        apply_volume_filter(context, frames["5m"])
    apply_timeframe_filter(context, frames)
    context["long_score"] = _clamp(context["long_score"])
    context["short_score"] = _clamp(context["short_score"])

    pricing = _pricing(frames.get("5m", {}).get("close", 0.0), market)
    entry = float(market.get("current_price") or market.get("last_price") or frames.get("5m", {}).get("close") or 0)
    result = {
        "symbol": context["symbol"],
        "direction": "HOLD",
        "market_mode": market_mode,
        "entry_grade": "F",
        "long_score": round(context["long_score"], 2),
        "short_score": round(context["short_score"], 2),
        "entry_price": entry,
        "stop_loss": None,
        "take_profit_1": None,
        "take_profit_2": None,
        "take_profit_3": None,
        "position_size_ratio": context["position_size_ratio"],
        "risk_reward_ratio": None,
        "risk_blocker": context["risk_blocker"],
        "warnings": context["warnings"],
        "reasons": context["reasons"],
        "timeframe_summary": frames,
        **pricing,
    }
    decide_final_direction(result)
    if result["direction"] == "LONG":
        result["entry_price"] = result["expected_entry_long"]
    elif result["direction"] == "SHORT":
        result["entry_price"] = result["expected_entry_short"]
    calculate_stop_loss_take_profit(result, context)
    apply_risk_filter(result, context)
    result["risk_blocker"] = context["risk_blocker"]
    decide_final_direction(result)
    calculate_entry_grade(result, context)
    result["long_score"] = round(_clamp(context["long_score"]), 2)
    result["short_score"] = round(_clamp(context["short_score"]), 2)
    result["position_size_ratio"] = context["position_size_ratio"]
    result["warnings"] = list(dict.fromkeys(context["warnings"]))
    result["reasons"] = list(dict.fromkeys(context["reasons"] + [f"최종 점수 LONG {result['long_score']} / SHORT {result['short_score']}"]))
    return result


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
        signal = analyze_scalping_signal(
            {
                "symbol": SYMBOL,
                "candles_by_timeframe": candles_by_timeframe,
                "market": market or {},
                "all_time_high": all_time_high,
                "all_time_low": all_time_low,
                "account_equity": account_equity,
            }
        )
        return self._to_result(signal, market or {}, account_equity, all_time_high, all_time_low)

    @staticmethod
    def _to_result(signal: dict, market: dict, equity: Optional[float], ath: Optional[float], atl: Optional[float]) -> TradingResult:
        direction = signal["direction"]
        entry = _num(signal.get("entry_price"))
        stop = signal.get("stop_loss")
        stop_distance = abs(entry - stop) if stop and entry > 0 else 0.0
        max_loss = float(equity or 1000.0) * 0.01 * signal.get("position_size_ratio", 1.0)
        size = max_loss / stop_distance if direction in ("LONG", "SHORT") and stop_distance > 0 else None
        value = size * entry if size else None
        fee = value * float(market.get("fee_rate") or TAKER_FEE_RATE) * 2 if value else None
        funding_fee = value * abs(float(market.get("funding_rate") or 0.0)) if value else None
        rr = signal.get("risk_reward_ratio")
        net_rr = rr - ((fee or 0) + (funding_fee or 0)) / max_loss if rr and max_loss > 0 else rr
        liq = signal.get("liquidation_price") or market.get("liquidation_price")
        liq_gap = signal.get("liquidation_gap")
        if liq and entry > 0 and not liq_gap:
            liq_gap = abs(entry - float(liq)) / entry
        timestamp = int(signal.get("timeframe_summary", {}).get("5m", {}).get("timestamp") or 0)
        long_score = _num(signal.get("long_score"), 50.0)
        short_score = _num(signal.get("short_score"), 50.0)
        return TradingResult(
            timestamp=timestamp,
            entry_price=round(entry, 2),
            direction=direction,
            long_probability=round(long_score, 2),
            short_probability=round(short_score, 2),
            confidence=round(abs(long_score - short_score), 2),
            stop_loss=round(stop, 2) if stop else None,
            take_profit_1=round(signal["take_profit_1"], 2) if signal.get("take_profit_1") else None,
            take_profit_2=round(signal["take_profit_2"], 2) if signal.get("take_profit_2") else None,
            risk_reward_ratio=round(rr, 2) if rr else None,
            all_time_high_mode=bool(ath and entry >= ath),
            all_time_low_mode=bool(atl and entry <= atl),
            timeframe_directions={tf: frame.get("direction", "HOLD") for tf, frame in signal.get("timeframe_summary", {}).items()},
            reasons=signal.get("reasons", []),
            analysis_price=round(_num(signal.get("last_price"), entry), 2),
            last_price=signal.get("last_price"),
            mark_price=signal.get("mark_price"),
            index_price=signal.get("index_price"),
            best_bid=signal.get("best_bid"),
            best_ask=signal.get("best_ask"),
            expected_entry_long=signal.get("expected_entry_long"),
            expected_entry_short=signal.get("expected_entry_short"),
            take_profit_3=round(signal["take_profit_3"], 2) if signal.get("take_profit_3") else None,
            long_score=round(long_score, 2),
            short_score=round(short_score, 2),
            entry_grade=signal.get("entry_grade", "F"),
            risk_warnings=signal.get("warnings", []),
            spread_rate=signal.get("spread_rate"),
            funding_rate=market.get("funding_rate"),
            estimated_fee=round(fee, 4) if fee is not None else None,
            estimated_funding_fee=round(funding_fee, 4) if funding_fee is not None else None,
            net_risk_reward=round(net_rr, 2) if net_rr else None,
            position_size_btc=round(size, 6) if size else None,
            position_value=round(value, 2) if value else None,
            max_loss_usdt=round(max_loss, 2),
            leverage=int(market.get("leverage") or 3),
            liquidation_price=round(float(liq), 2) if liq else None,
            liquidation_gap=round(float(liq_gap), 4) if liq_gap else None,
            stop_gap=round(signal["stop_gap"], 4) if signal.get("stop_gap") else None,
            market_mode=signal.get("market_mode", "HOLD"),
            position_size_ratio=signal.get("position_size_ratio", 1.0),
            timeframe_summary=signal.get("timeframe_summary", {}),
        )

    def _calc_risk_prices(self, direction: str, entry: float, candles: list[dict]) -> tuple:
        frame = analyze_timeframe(candles, "5m")
        context = {
            "frames": {"5m": frame},
            "market_mode": "TREND_LONG" if direction == "LONG" else "TREND_SHORT",
            "warnings": [],
            "risk_blocker": False,
        }
        result = {"direction": direction, "entry_price": entry}
        calculate_stop_loss_take_profit(result, context)
        return result.get("stop_loss"), result.get("take_profit_1"), result.get("take_profit_2"), result.get("take_profit_3")
