# 역할: Bitget 선물 API 연동을 담당하는 파일.
from backend.bitget.client import BitgetPrivateClient


class PositionApi:
    def __init__(self, client: BitgetPrivateClient):
        self.client = client

    def get_account(self) -> dict:
        return self.client.get_account()

    def get_positions(self) -> list[dict]:
        return self.client.get_positions()

    def close_position(self, hold_side: str) -> dict:
        return self.client.close_position(hold_side)


__all__ = ["PositionApi"]
