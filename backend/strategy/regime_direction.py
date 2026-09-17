"""횡보·중립 장세에서 진입 방향을 반대로 적용하는 공통 규칙."""
from __future__ import annotations


UNCERTAIN_REGIMES = frozenset({"RANGE", "NEUTRAL"})


def should_reverse_uncertain_direction(
    market_regime: str | None,
    raw_market_regime: str | None = None,
) -> bool:
    """확정 횡보 또는 최신 중립/횡보 판정이면 역방향 진입을 사용한다."""
    stable = str(market_regime or "").upper()
    raw = str(raw_market_regime or "").upper()
    return stable == "RANGE" or raw in UNCERTAIN_REGIMES


def reverse_uncertain_direction(
    direction: str,
    market_regime: str | None,
    raw_market_regime: str | None = None,
) -> tuple[str, bool]:
    """LONG/SHORT만 반전하고 반전 적용 여부를 함께 반환한다."""
    normalized = str(direction or "HOLD").upper()
    if (
        normalized not in ("LONG", "SHORT")
        or not should_reverse_uncertain_direction(market_regime, raw_market_regime)
    ):
        return normalized, False
    return ("SHORT" if normalized == "LONG" else "LONG"), True


__all__ = [
    "UNCERTAIN_REGIMES",
    "reverse_uncertain_direction",
    "should_reverse_uncertain_direction",
]
