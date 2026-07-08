# 역할: 실거래 전 paper trading을 기본값으로 사용하는 주문 인터페이스입니다.
from dataclasses import dataclass
from typing import Optional


@dataclass
class OrderResult:
    ok: bool
    mode: str
    action: str
    direction: str
    size: float
    price: float
    message: str


class OrderManager:
    def __init__(self, private_client=None, paper_trading: bool = True):
        self.private_client = private_client
        self.paper_trading = paper_trading
        self.position: Optional[dict] = None

    def place_long(self, size: float, price: float, signal: dict | None = None) -> OrderResult:
        return self._open("LONG", size, price, signal)

    def place_short(self, size: float, price: float, signal: dict | None = None) -> OrderResult:
        return self._open("SHORT", size, price, signal)

    def close_position(self, price: float, reason: str = "") -> OrderResult:
        if not self.position:
            return OrderResult(False, self._mode, "close", "HOLD", 0.0, price, "청산할 포지션 없음")
        direction = self.position["direction"]
        size = self.position["size"]
        if self.paper_trading:
            self.position = None
            return OrderResult(True, self._mode, "close", direction, size, price, reason or "paper position closed")
        if self.private_client is None:
            return OrderResult(False, self._mode, "close", direction, size, price, "실거래 client 없음")
        self.private_client.close_position("long" if direction == "LONG" else "short")
        self.position = None
        return OrderResult(True, self._mode, "close", direction, size, price, reason or "live position closed")

    @property
    def _mode(self) -> str:
        return "PAPER" if self.paper_trading else "LIVE"

    def _open(self, direction: str, size: float, price: float, signal: dict | None) -> OrderResult:
        if size <= 0:
            return OrderResult(False, self._mode, "open", direction, size, price, "주문 수량 없음")
        if self.position:
            return OrderResult(False, self._mode, "open", direction, size, price, "기존 포지션 보유 중")
        if self.paper_trading:
            self.position = {"direction": direction, "size": size, "entry": price, "signal": signal or {}}
            return OrderResult(True, self._mode, "open", direction, size, price, "paper order opened")
        if self.private_client is None:
            return OrderResult(False, self._mode, "open", direction, size, price, "실거래 client 없음")
        side = "buy" if direction == "LONG" else "sell"
        self.private_client.place_market_order(side, f"{size:.3f}", "open")
        self.position = {"direction": direction, "size": size, "entry": price, "signal": signal or {}}
        return OrderResult(True, self._mode, "open", direction, size, price, "live order opened")


__all__ = ["OrderManager", "OrderResult"]
