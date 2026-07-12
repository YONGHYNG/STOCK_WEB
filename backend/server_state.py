# 역할: 서버와 자동매매 실행 상태를 공유하는 파일.
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TradingState:
    last_result: Optional[dict] = None
    last_price: Optional[float] = None
    seeded: bool = False
    auto_trade_enabled: bool = True
    trading_mode: str = "PAPER_TRADING"
    open_trade_id: Optional[int] = None
    open_trade_data: Optional[dict] = None
    plan_trade_id: Optional[int] = None
    plan_trade_data: Optional[dict] = None
    plan_signature: Optional[tuple] = None
    paper_account_start_trade_id: Optional[int] = None
    cached_account: Optional[dict] = None
    cached_positions: list = field(default_factory=list)
    emergency_stopped: bool = False
    auto_trade_enabled_before_emergency: Optional[bool] = None
    _log_buffer: list = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add_log(self, message: str) -> str:
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        with self._lock:
            self._log_buffer.append(entry)
            if len(self._log_buffer) > 500:
                self._log_buffer = self._log_buffer[-500:]
        return entry

    def get_logs(self, last_n: int = 200) -> list[str]:
        with self._lock:
            return list(self._log_buffer[-last_n:])


state = TradingState()
