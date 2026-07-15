# 역할: API 요청과 응답 데이터 구조를 정의하는 스키마.
from typing import Optional

from pydantic import BaseModel


class RiskSettingsPayload(BaseModel):
    order_size_btc: float
    max_loss_pct: float
    daily_max_loss_pct: float
    consecutive_loss_limit: int
    confidence_threshold: float
    reentry_wait_seconds: int
    stop_gap_min_usdt: float = 400.0
    stop_gap_max_usdt: float = 700.0
    take_profit_1_min_usdt: float = 500.0
    take_profit_1_max_usdt: float = 600.0
    take_profit_2_usdt: float = 800.0
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


class BacktestPayload(BaseModel):
    start_ts: int
    end_ts: int
    timeframe: str
    initial_capital: float
    fee_rate: float
    slippage: float
    order_size_pct: float
