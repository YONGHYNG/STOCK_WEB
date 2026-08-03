# 역할: API 요청과 응답 데이터 구조를 정의하는 스키마.
from typing import Optional

from pydantic import BaseModel, Field


class StrategySettingPayload(BaseModel):
    id: str
    name: str
    description: str = ""
    enabled: bool = True


class RiskSettingsPayload(BaseModel):
    strategies: list[StrategySettingPayload] = Field(default_factory=list)
    order_size_btc: float
    risk_per_trade_pct: float = 0.2
    max_loss_pct: float
    daily_max_loss_pct: float
    consecutive_loss_limit: int
    confidence_threshold: float
    reentry_wait_seconds: int
    stop_reentry_wait_seconds: int = 900
    take_profit_reentry_wait_seconds: int = 300
    two_loss_pause_seconds: int = 3600
    stop_gap_min_usdt: float = 400.0
    stop_gap_max_usdt: float = 700.0
    take_profit_1_min_usdt: float = 500.0
    take_profit_1_max_usdt: float = 600.0
    take_profit_2_usdt: float = 800.0
    atr_stop_multiplier: float = 1.5
    max_ma_distance_atr: float = 2.0
    oi_sharp_drop_pct: float = 2.0
    max_leverage: int
    live_trading_allowed: bool


class ModePayload(BaseModel):
    mode: str


class AutoTradePayload(BaseModel):
    enabled: bool
    threshold: Optional[float] = None


class CredentialsPayload(BaseModel):
    api_key: str
    secret_key: str
    passphrase: str


class OrderPayload(BaseModel):
    side: str
    size: float


class PaperPendingOrderPayload(BaseModel):
    direction: str
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float


class BacktestPayload(BaseModel):
    start_ts: int
    end_ts: int
    timeframe: str
    initial_capital: float
    fee_rate: float
    slippage: float
    order_size_pct: float
