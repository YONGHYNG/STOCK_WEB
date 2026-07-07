class StopLossManager:
    @staticmethod
    def is_stop_hit(direction: str, price: float, stop_loss: float | None) -> bool:
        if stop_loss is None:
            return False
        if direction == "LONG":
            return price <= stop_loss
        if direction == "SHORT":
            return price >= stop_loss
        return False


__all__ = ["StopLossManager"]
