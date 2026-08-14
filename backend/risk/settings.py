# 역할: 리스크 설정값을 저장하고 불러오는 파일.
"""
리스크 관리 설정 - data/risk_settings.json 에 저장/로드
"""

import json
from dataclasses import dataclass, asdict, field
from backend.config import DATA_DIR

_RISK_FILE = DATA_DIR / "risk_settings.json"

DEFAULT_STRATEGIES = [
    {"id": "trend_continuation", "name": "추세 지속", "description": "EMA20·VWAP 눌림목에서 기존 추세 방향으로 진입", "enabled": True},
    {"id": "rsi_reversal", "name": "RSI 재돌파·재이탈", "description": "RSI 50선 전환과 EMA·VWAP 정렬을 확인해 진입", "enabled": True},
    {"id": "volume_breakout", "name": "거래량 돌파", "description": "거래량과 ADX가 동반된 돌파 및 재테스트에 진입", "enabled": True},
    {"id": "range_reversion", "name": "횡보장 밴드 반전", "description": "낮은 ADX 구간에서 볼린저밴드 반전을 거래", "enabled": True},
    {"id": "neutral_momentum", "name": "중립장 모멘텀", "description": "장세 전환 과정의 강한 단기 모멘텀에 진입", "enabled": True},
]


@dataclass
class RiskSettings:
    strategies: list[dict] = field(default_factory=lambda: [dict(item) for item in DEFAULT_STRATEGIES])
    # 주문 규모
    order_size_btc: float = 0.001       # 1회 주문 수량 (BTC)
    risk_per_trade_pct: float = 0.2     # 계좌 잔액 기준 1회 위험률 (%)

    # 손실 제한
    max_loss_pct: float = 1.0           # 1회 최대 손실률 (%)
    daily_max_loss_pct: float = 3.0     # 일일 최대 손실률 (%)
    consecutive_loss_limit: int = 3     # 연속 손실 정지 횟수
    auto_stop_loss_analysis: bool = True  # 손절 누락 복구 및 원인 자동 기록

    # 진입 조건
    confidence_threshold: float = 30.0  # 자동매매 확정 신호 기준 (%)
    reentry_wait_seconds: int = 1800    # 재진입 대기 시간 (초)
    stop_reentry_wait_seconds: int = 600
    take_profit_reentry_wait_seconds: int = 180
    two_loss_pause_seconds: int = 1800

    # 진입가 기준 가격 간격 (USDT)
    stop_gap_min_usdt: float = 400.0
    stop_gap_max_usdt: float = 700.0
    take_profit_1_min_usdt: float = 500.0
    take_profit_1_max_usdt: float = 600.0
    take_profit_2_usdt: float = 800.0
    atr_stop_multiplier: float = 1.5
    max_ma_distance_atr: float = 2.5
    oi_sharp_drop_pct: float = 2.0

    # 레버리지
    max_leverage: int = 20              # 최대 레버리지

    # 실거래 허용
    live_trading_allowed: bool = False  # 실거래 주문 허용 여부 (명시적 동의)


def load() -> RiskSettings:
    if _RISK_FILE.exists():
        try:
            with open(_RISK_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            return RiskSettings(
                strategies            = [dict(item) for item in d.get("strategies", DEFAULT_STRATEGIES)],
                order_size_btc        = float(d.get("order_size_btc",        0.001)),
                risk_per_trade_pct    = float(d.get("risk_per_trade_pct",    0.2)),
                max_loss_pct          = float(d.get("max_loss_pct",          1.0)),
                daily_max_loss_pct    = float(d.get("daily_max_loss_pct",    3.0)),
                consecutive_loss_limit= 3,
                auto_stop_loss_analysis = bool(d.get("auto_stop_loss_analysis", True)),
                confidence_threshold  = float(d.get("confidence_threshold",  30.0)),
                reentry_wait_seconds  = int(d.get("reentry_wait_seconds", 900)),
                stop_reentry_wait_seconds = int(d.get("stop_reentry_wait_seconds", 600)),
                take_profit_reentry_wait_seconds = int(d.get("take_profit_reentry_wait_seconds", 180)),
                two_loss_pause_seconds = int(d.get("two_loss_pause_seconds", 1800)),
                stop_gap_min_usdt     = float(d.get("stop_gap_min_usdt",     400.0)),
                stop_gap_max_usdt     = float(d.get("stop_gap_max_usdt",     700.0)),
                take_profit_1_min_usdt= float(d.get("take_profit_1_min_usdt",500.0)),
                take_profit_1_max_usdt= float(d.get("take_profit_1_max_usdt",600.0)),
                take_profit_2_usdt    = float(d.get("take_profit_2_usdt",    800.0)),
                atr_stop_multiplier   = float(d.get("atr_stop_multiplier",   1.5)),
                max_ma_distance_atr   = float(d.get("max_ma_distance_atr",   2.5)),
                oi_sharp_drop_pct     = float(d.get("oi_sharp_drop_pct",     2.0)),
                max_leverage          = int(  d.get("max_leverage",          20)),
                live_trading_allowed  = bool( d.get("live_trading_allowed",  False)),
            )
        except Exception:
            pass
    return RiskSettings()


def save(s: RiskSettings) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_RISK_FILE, "w", encoding="utf-8") as f:
        json.dump(asdict(s), f, indent=2, ensure_ascii=False)
