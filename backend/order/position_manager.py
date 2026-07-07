# 역할: 현재 포지션 상태와 진입 정보를 관리하는 파일.
from backend.bitget.client import BitgetPrivateClient
from backend.config import SYMBOL


class PositionManager:
    def __init__(self, client: BitgetPrivateClient):
        self.client = client

    def btc_positions(self) -> list[dict]:
        return [p for p in self.client.get_positions() if p.get("symbol") == SYMBOL]

    def close(self, hold_side: str) -> dict:
        return self.client.close_position(hold_side)


__all__ = ["PositionManager"]
