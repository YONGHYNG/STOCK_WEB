# 역할: 연속 손실과 일일 손실 제한을 관리하는 보호 장치.
class ConsecutiveLossGuard:
    def __init__(self, limit: int):
        self.limit = limit
        self.losses = 0

    def record(self, pnl_pct: float) -> None:
        self.losses = self.losses + 1 if pnl_pct < 0 else 0

    @property
    def blocked(self) -> bool:
        return self.losses >= self.limit


__all__ = ["ConsecutiveLossGuard"]
