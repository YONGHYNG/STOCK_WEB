"""한국시간 고정 진입 세션과 강제 진입 방향/가격 계획을 계산한다."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
SCHEDULED_ENTRY_WINDOWS = (
    ("MORNING", time(8, 50), time(9, 20)),
    ("EUROPE", time(16, 0), time(17, 0)),
    ("US", time(23, 40), time(0, 20)),
)


def active_scheduled_session(now: Optional[datetime] = None) -> Optional[tuple[str, str]]:
    """현재 KST 시각의 (세션 기준일, 세션키)를 반환한다."""
    current = now.astimezone(KST) if now else datetime.now(KST)
    current_time = current.time().replace(tzinfo=None)
    for key, start, end in SCHEDULED_ENTRY_WINDOWS:
        if start <= end:
            active = start <= current_time <= end
            session_date = current.date()
        else:
            active = current_time >= start or current_time <= end
            session_date = current.date() if current_time >= start else current.date() - timedelta(days=1)
        if active:
            return session_date.isoformat(), key
    return None


def choose_forced_direction(result: dict) -> str:
    """확정 신호가 없을 때에도 최신 지표와 시간봉 투표로 방향을 결정한다."""
    direction = str(result.get("direction") or "HOLD").upper()
    if direction in ("LONG", "SHORT"):
        return direction

    long_score = float(result.get("long_probability") or 0)
    short_score = float(result.get("short_probability") or 0)
    diagnostics = result.get("diagnostics") or {}
    metrics = diagnostics.get("metrics") or {}
    close = float(metrics.get("close") or result.get("entry_price") or 0)
    ema20 = float(metrics.get("ema20") or 0)
    ema50 = float(metrics.get("ema50") or 0)
    vwap = float(metrics.get("vwap") or 0)
    slope = float(metrics.get("ema20_slope") or 0)
    if ema20 and ema50:
        (long_score := long_score + 2) if ema20 >= ema50 else (short_score := short_score + 2)
    if close and vwap:
        (long_score := long_score + 1) if close >= vwap else (short_score := short_score + 1)
    if slope:
        (long_score := long_score + 1) if slope > 0 else (short_score := short_score + 1)
    for tf, vote in (result.get("timeframe_directions") or {}).items():
        weight = 2 if tf in ("15m", "1H", "4H") else 1
        if vote == "LONG":
            long_score += weight
        elif vote == "SHORT":
            short_score += weight
    return "LONG" if long_score >= short_score else "SHORT"


def build_forced_entry_result(result: dict, price: float, direction: str, session_key: str, settings) -> dict:
    """현재가 진입용 SL/TP가 방향과 일치하도록 새 결과를 만든다."""
    entry = float(price)
    stop_gap = (float(settings.stop_gap_min_usdt) + float(settings.stop_gap_max_usdt)) / 2
    tp1_gap = (float(settings.take_profit_1_min_usdt) + float(settings.take_profit_1_max_usdt)) / 2
    tp2_gap = float(settings.take_profit_2_usdt)
    forced = dict(result)
    forced.update({
        "direction": direction,
        "entry_price": entry,
        "stop_loss": entry - stop_gap if direction == "LONG" else entry + stop_gap,
        "take_profit_1": entry + tp1_gap if direction == "LONG" else entry - tp1_gap,
        "take_profit_2": entry + tp2_gap if direction == "LONG" else entry - tp2_gap,
        "risk_reward_ratio": round(tp1_gap / stop_gap, 3),
        "confidence": max(float(result.get("confidence") or 0), 30.0),
        "entry_grade": "SCHEDULED",
        "strategy_signal": f"SCHEDULED_{session_key}_{direction}",
        "reasons": [
            f"고정 진입 세션 {session_key}: 포지션 없음 → 현재가 강제 진입",
            f"최신 지표·시간봉 방향 선택: {direction}",
        ],
    })
    return forced
