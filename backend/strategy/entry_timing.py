"""Closed-candle entry confirmation, shared by normal and scheduled orders.

Thresholds are initial engineering defaults, not fitted profitability claims.
Input frames must contain only completed, ascending five-minute candles.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import pandas as pd

BAR_MS = 300_000
ENTRY_TIMING_LOOKBACK_BARS = 60
STRUCTURE_BREAK_LOOKBACK_BARS = 36
STRUCTURE_LEVEL_LOOKBACK_BARS = 18
RETEST_LOOKBACK_BARS = 12
PULLBACK_LOOKBACK_BARS = 12
TOUCH_TOLERANCE_ATR = 0.20
MAX_ANCHOR_DISTANCE_ATR = 0.75
MAX_CHASE_ATR = 0.25


def assess_entry_timing(frame: pd.DataFrame, direction: str, directions: dict) -> dict:
    result = {"confirmed": False, "direction": direction, "reason": "확정 5분봉 타점 데이터 부족"}
    required = ["timestamp", "open", "high", "low", "close", "atr14", "ema20", "vwap"]
    if (
        direction not in ("LONG", "SHORT")
        or len(frame) < ENTRY_TIMING_LOOKBACK_BARS
        or any(k not in frame for k in required)
    ):
        return result
    recent = frame.iloc[-ENTRY_TIMING_LOOKBACK_BARS:]
    if not all(math.isfinite(float(v)) for v in recent[required].to_numpy().ravel()):
        return result
    if not (recent.timestamp.diff().dropna() == BAR_MS).all():
        result["reason"] = "5분봉 누락 또는 중복으로 타점 확인 대기"
        return result
    last, prev = frame.iloc[-1], frame.iloc[-2]
    atr = float(last.atr14)
    if atr <= 0:
        return result
    long = direction == "LONG"
    opposite = "SHORT" if long else "LONG"
    opposing = [tf for tf in ("15m", "30m", "1H", "4H", "6H") if directions.get(tf) == opposite]
    result.update(timestamp=int(last.timestamp), atr=atr, confirmation_price=float(last.close), opposing_frames=opposing)
    resumed = (last.close > prev.high and last.close > last.open) if long else (last.close < prev.low and last.close < last.open)
    if not resumed:
        result["reason"] = "직전 5분봉 고점 위 종가 확인 대기" if long else "직전 5분봉 저점 아래 종가 확인 대기"
        return result

    setups = []
    # A break must precede a separate retest. The breakout level uses only
    # candles preceding that break; no centered pivots or future candles.
    for b in range(len(frame) - STRUCTURE_BREAK_LOOKBACK_BARS, len(frame) - 2):
        history = frame.iloc[b - STRUCTURE_LEVEL_LOOKBACK_BARS:b]
        level = float(history.high.max() if long else history.low.min())
        bar = frame.iloc[b]
        crossed = bar.close > level and frame.iloc[b - 1].close <= level if long else bar.close < level and frame.iloc[b - 1].close >= level
        if not crossed:
            continue
        for t in range(max(b + 1, len(frame) - RETEST_LOOKBACK_BARS), len(frame) - 1):
            touch = frame.iloc[t]
            held = frame.iloc[b + 1:]
            if long:
                valid = (level - atr * .2 <= touch.low <= level + atr * .2
                         and (held.close >= level).all()
                         and held.low.min() > history.low.min())
            else:
                valid = (level - atr * .2 <= touch.high <= level + atr * .2
                         and (held.close <= level).all()
                         and held.high.max() < history.high.max())
            if valid:
                setups.append((t, level, "STRUCTURE_RETEST", int(bar.timestamp)))

    # Countertrend entries require the structural break/retest above.
    if not opposing:
        for t in range(len(frame) - PULLBACK_LOOKBACK_BARS, len(frame) - 1):
            touch, before = frame.iloc[t], frame.iloc[t - 1]
            retracing = touch.low < before.low and touch.close < before.close if long else touch.high > before.high and touch.close > before.close
            if not retracing:
                continue
            for key in ("ema20", "vwap"):
                level = float(touch[key])
                extreme = float(touch.low if long else touch.high)
                held = frame.iloc[t:]
                if (level > 0 and abs(extreme - level) <= atr * TOUCH_TOLERANCE_ATR
                        and ((held.close >= level).all() if long else (held.close <= level).all())):
                    setups.append((t, level, "PULLBACK_CONFIRMATION", int(touch.timestamp)))
    # Prefer the newest qualifying setup, within the chase limit.
    for t, level, kind, setup_start in sorted(setups, reverse=True):
        distance = (float(last.close) - level) * (1 if long else -1)
        if not 0 <= distance <= atr * MAX_ANCHOR_DISTANCE_ATR:
            continue
        held = frame.iloc[t:]
        result.update(confirmed=True, kind=kind, setup_start=setup_start,
                      anchor=level, invalidation_price=float(held.low.min() if long else held.high.max()),
                      reason="구조 돌파·재테스트 후 재출발 확인" if kind == "STRUCTURE_RETEST" else "눌림·반등 지지저항 후 재출발 확인")
        return result
    result["reason"] = "상위 추세 반대: 구조 전환·재테스트 확인 대기" if opposing else "새 눌림·재테스트 대기 또는 기준선 대비 추격 거리 초과"
    return result


def timing_entry_check(timing: dict, price: float, now_ms: int | None = None,
                       last_exit: dict | None = None) -> tuple[bool, str]:
    if not timing.get("confirmed"):
        return False, timing.get("reason") or "확정 타점 없음"
    try:
        stamp = int(timing["timestamp"])
        atr = float(timing["atr"])
        confirmation = float(timing["confirmation_price"])
        invalidation = float(timing["invalidation_price"])
        price = float(price)
        if not all(math.isfinite(v) for v in (atr, price, confirmation, invalidation)) or atr <= 0 or price <= 0:
            return False, "타점 가격 데이터 오류"
        if now_ms is not None and not stamp + BAR_MS <= now_ms < stamp + BAR_MS * 2:
            return False, "타점 확인봉 유효시간 경과 또는 미완성 봉"
        long = timing["direction"] == "LONG"
        if (price - confirmation) * (1 if long else -1) > atr * MAX_CHASE_ATR:
            return False, "확인 종가에서 0.25 ATR 초과 추격 진입 차단"
        if (price <= invalidation if long else price >= invalidation):
            return False, "지지·저항 구조 이탈로 타점 무효"
        if last_exit and last_exit.get("direction") == timing["direction"] and float(last_exit.get("pnl_pct") or 0) > 0:
            exited = datetime.fromisoformat(last_exit["exit_time"]).replace(tzinfo=timezone.utc)
            if int(timing["setup_start"]) < int(exited.timestamp() * 1000):
                return False, "익절 이후 새 눌림·돌파 재테스트가 없어 동일 방향 재진입 차단"
    except (KeyError, TypeError, ValueError, OverflowError):
        return False, "타점 또는 최근 청산 데이터 오류"
    return True, timing["reason"]


def scheduled_timing_check(timing: dict, price: float, force_due: bool,
                           now_ms: int, last_exit: dict | None = None) -> tuple[bool, str, str]:
    allowed, reason = timing_entry_check(timing, price, now_ms, last_exit)
    if allowed:
        return True, "CONFIRMED", reason
    if force_due:
        return True, "DEADLINE_OVERRIDE", f"정시 마감 예외 진입 · 미충족 타점: {reason}"
    return False, "WAIT", reason
