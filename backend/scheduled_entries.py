"""한국시간 고정 진입 세션과 강제 진입 방향/가격 계획을 계산한다."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
SCHEDULED_ENTRY_WINDOWS = (
    ("MORNING", time(8, 58), time(9, 28)),
    ("EUROPE", time(16, 30), time(17, 0)),
    ("US", time(23, 40), time(0, 20)),
)
SCHEDULED_SPLIT_ENTRY_BEFORE_END_SECONDS = 10 * 60
SCALP_STOP_ATR_MULTIPLIER = 0.8
SCALP_STOP_GAP_MIN_USDT = 450.0
SCALP_STOP_GAP_MAX_USDT = 600.0
SCALP_TP1_RISK_RATIO = 1.2
SCALP_TP2_RISK_RATIO = 1.5
SCALP_ADD_ON_RISK_RATIO = 0.35


def scheduled_session_bounds(session_date: str, session_key: str) -> tuple[datetime, datetime]:
    """세션 기준일과 키로 KST 시작·종료 시각을 계산한다."""
    base_date = date.fromisoformat(session_date)
    for key, start, end in SCHEDULED_ENTRY_WINDOWS:
        if key != session_key:
            continue
        start_at = datetime.combine(base_date, start, tzinfo=KST)
        end_at = datetime.combine(base_date, end, tzinfo=KST)
        if end < start:
            end_at += timedelta(days=1)
        return start_at, end_at
    raise ValueError(f"알 수 없는 고정 진입 세션: {session_key}")


def seconds_until_session_end(
    session_date: str,
    session_key: str,
    now: Optional[datetime] = None,
) -> float:
    """현재 KST 시각부터 세션 종료까지 남은 초를 반환한다."""
    current = now.astimezone(KST) if now else datetime.now(KST)
    _, end_at = scheduled_session_bounds(session_date, session_key)
    return (end_at - current).total_seconds()


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
    timeframe_weights = {
        "1m": 1, "5m": 3, "15m": 4, "30m": 2,
        "1H": 2, "4H": 1, "6H": 1, "1D": 1,
    }
    for tf, vote in (result.get("timeframe_directions") or {}).items():
        weight = timeframe_weights.get(tf, 1)
        if vote == "LONG":
            long_score += weight
        elif vote == "SHORT":
            short_score += weight
    return "LONG" if long_score >= short_score else "SHORT"


def direction_bias_score(result: dict) -> float:
    """한 번의 분석 결과를 LONG(+) / SHORT(-) 방향 점수로 변환한다."""
    direction = str(result.get("direction") or "HOLD").upper()
    score = float(result.get("long_probability") or 0) - float(result.get("short_probability") or 0)
    if direction == "LONG":
        score += 25
    elif direction == "SHORT":
        score -= 25

    diagnostics = result.get("diagnostics") or {}
    metrics = diagnostics.get("metrics") or {}
    close = float(metrics.get("close") or result.get("entry_price") or 0)
    ema20 = float(metrics.get("ema20") or 0)
    ema50 = float(metrics.get("ema50") or 0)
    vwap = float(metrics.get("vwap") or 0)
    slope = float(metrics.get("ema20_slope") or 0)
    if ema20 and ema50:
        score += 3 if ema20 >= ema50 else -3
    if close and vwap:
        score += 2 if close >= vwap else -2
    if slope:
        score += 2 if slope > 0 else -2

    # 고정 세션은 수십 분 안에 끝내는 단타이므로 5m·15m에 가장 큰
    # 가중치를 주고, 4H 이상은 방향을 뒤집지 않는 보조 필터로만 쓴다.
    timeframe_weights = {
        "1m": 1, "5m": 3, "15m": 4, "30m": 2,
        "1H": 2, "4H": 1, "6H": 1, "1D": 1,
    }
    for timeframe, vote in (result.get("timeframe_directions") or {}).items():
        weight = timeframe_weights.get(timeframe, 1)
        if vote == "LONG":
            score += weight
        elif vote == "SHORT":
            score -= weight
    return score


def choose_consensus_direction(results: list[dict]) -> tuple[str, float]:
    """여러 분석을 합산하되 단타 방향인 최신 5m·15m 합의를 우선한다."""
    usable = [result for result in results if result]
    if not usable:
        return "LONG", 0.0
    total = 0.0
    for index, result in enumerate(usable, start=1):
        # 최근 분석일수록 조금 더 크게 반영한다.
        recency_weight = 1.0 + (index - 1) * 0.25
        total += direction_bias_score(result) * recency_weight
    latest = usable[-1]
    directions = latest.get("timeframe_directions") or {}
    five_min = str(directions.get("5m") or "HOLD").upper()
    fifteen_min = str(directions.get("15m") or "HOLD").upper()
    if five_min == fifteen_min and five_min in ("LONG", "SHORT"):
        return five_min, total
    if fifteen_min in ("LONG", "SHORT"):
        return fifteen_min, total
    if total == 0:
        return choose_forced_direction(latest), total
    return ("LONG" if total > 0 else "SHORT"), total


def _scheduled_atr(result: dict) -> float:
    metrics = (result.get("diagnostics") or {}).get("metrics") or {}
    for value in (metrics.get("atr14"), result.get("atr14")):
        try:
            atr = float(value or 0)
        except (TypeError, ValueError):
            continue
        if atr > 0:
            return atr
    return 0.0


def build_forced_entry_result(result: dict, price: float, direction: str, session_key: str, settings) -> dict:
    """고정 세션 단타용 5분 ATR 손절·익절 계획을 만든다."""
    entry = float(price)
    atr = _scheduled_atr(result)
    fallback_gap = (SCALP_STOP_GAP_MIN_USDT + SCALP_STOP_GAP_MAX_USDT) / 2
    stop_gap = (
        min(max(atr * SCALP_STOP_ATR_MULTIPLIER, SCALP_STOP_GAP_MIN_USDT), SCALP_STOP_GAP_MAX_USDT)
        if atr else fallback_gap
    )
    tp1_gap = stop_gap * SCALP_TP1_RISK_RATIO
    tp2_gap = stop_gap * SCALP_TP2_RISK_RATIO
    forced = dict(result)
    forced.update({
        "direction": direction,
        "entry_price": entry,
        "stop_loss": entry - stop_gap if direction == "LONG" else entry + stop_gap,
        "take_profit_1": entry + tp1_gap if direction == "LONG" else entry - tp1_gap,
        "take_profit_2": entry + tp2_gap if direction == "LONG" else entry - tp2_gap,
        "risk_reward_ratio": round(tp1_gap / stop_gap, 3),
        "scheduled_stop_gap": stop_gap,
        "scheduled_tp1_ratio": SCALP_TP1_RISK_RATIO,
        "scheduled_tp2_ratio": SCALP_TP2_RISK_RATIO,
        "scheduled_add_on_ratio": SCALP_ADD_ON_RISK_RATIO,
        "scalp_max_hold_seconds": 45 * 60,
        "scalp_no_progress_seconds": 15 * 60,
        "scalp_min_progress_ratio": 0.3,
        "position_size_percent": 100.0,
        "confidence": float(result.get("confidence") or 0),
        "entry_grade": "SCHEDULED_MANDATORY",
        "strategy_signal": f"SCHEDULED_{session_key}_{direction}",
        "reasons": [
            f"고정 진입 세션 {session_key}: 포지션 없음 → 현재가 강제 진입",
            f"최신 지표·시간봉 방향 선택: {direction}",
            f"5분 ATR 단타 손절 ${stop_gap:,.2f}, 목표 손익비 1:{tp1_gap / stop_gap:.1f}",
        ],
    })
    return forced


def reprice_scheduled_result(result: dict, average_entry: float) -> dict:
    """분할 체결 평균단가를 기준으로 SL/TP를 동일 위험 거리로 다시 계산한다."""
    repriced = dict(result)
    direction = str(repriced.get("direction") or "HOLD").upper()
    entry = float(average_entry)
    stop_gap = float(repriced.get("scheduled_stop_gap") or 0)
    if direction not in ("LONG", "SHORT") or entry <= 0 or stop_gap <= 0:
        return repriced
    tp1_gap = stop_gap * float(repriced.get("scheduled_tp1_ratio") or SCALP_TP1_RISK_RATIO)
    tp2_gap = stop_gap * float(repriced.get("scheduled_tp2_ratio") or SCALP_TP2_RISK_RATIO)
    repriced.update({
        "entry_price": entry,
        "stop_loss": entry - stop_gap if direction == "LONG" else entry + stop_gap,
        "take_profit_1": entry + tp1_gap if direction == "LONG" else entry - tp1_gap,
        "take_profit_2": entry + tp2_gap if direction == "LONG" else entry - tp2_gap,
    })
    return repriced
