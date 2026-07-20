# 역할: 리스크 설정값을 저장하고 불러오는 파일.
"""
리스크 관리 설정 - data/risk_settings.json 에 저장/로드
"""

import json
from dataclasses import dataclass, asdict
from backend.config import DATA_DIR

_RISK_FILE = DATA_DIR / "risk_settings.json"


@dataclass
class RiskSettings:
    # 주문 규모
    order_size_btc: float = 0.001       # 1회 주문 수량 (BTC)

    # 손실 제한
    max_loss_pct: float = 1.0           # 1회 최대 손실률 (%)
    daily_max_loss_pct: float = 3.0     # 일일 최대 손실률 (%)
    consecutive_loss_limit: int = 3     # 연속 손실 정지 횟수

    # 진입 조건
    confidence_threshold: float = 30.0  # 자동매매 확정 신호 기준 (%)
    reentry_wait_seconds: int = 1800    # 재진입 대기 시간 (초)

    # 진입가 기준 가격 간격 (USDT)
    stop_gap_min_usdt: float = 400.0
    stop_gap_max_usdt: float = 700.0
    take_profit_1_min_usdt: float = 500.0
    take_profit_1_max_usdt: float = 600.0
    take_profit_2_usdt: float = 800.0

    # 레버리지
    max_leverage: int = 3               # 최대 레버리지

    # 실거래 허용
    live_trading_allowed: bool = False  # 실거래 주문 허용 여부 (명시적 동의)


def load() -> RiskSettings:
    if _RISK_FILE.exists():
        try:
            with open(_RISK_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            return RiskSettings(
                order_size_btc        = float(d.get("order_size_btc",        0.001)),
                max_loss_pct          = float(d.get("max_loss_pct",          1.0)),
                daily_max_loss_pct    = float(d.get("daily_max_loss_pct",    3.0)),
                consecutive_loss_limit= 3,
                confidence_threshold  = float(d.get("confidence_threshold",  30.0)),
                reentry_wait_seconds  = max(1800, int(d.get("reentry_wait_seconds", 1800))),
                stop_gap_min_usdt     = float(d.get("stop_gap_min_usdt",     400.0)),
                stop_gap_max_usdt     = float(d.get("stop_gap_max_usdt",     700.0)),
                take_profit_1_min_usdt= float(d.get("take_profit_1_min_usdt",500.0)),
                take_profit_1_max_usdt= float(d.get("take_profit_1_max_usdt",600.0)),
                take_profit_2_usdt    = float(d.get("take_profit_2_usdt",    800.0)),
                max_leverage          = int(  d.get("max_leverage",          3)),
                live_trading_allowed  = bool( d.get("live_trading_allowed",  False)),
            )
        except Exception:
            pass
    return RiskSettings()


def save(s: RiskSettings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_RISK_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(s), f, indent=2, ensure_ascii=False)
