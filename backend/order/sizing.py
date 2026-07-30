"""실거래 주문 수량 계산."""

from decimal import Decimal, ROUND_DOWN
from typing import Union

NumberLike = Union[float, str]


def full_balance_size(
    available_usdt: NumberLike,
    leverage: int,
    entry_price: NumberLike,
    size_step: NumberLike,
    minimum_size: NumberLike,
) -> str:
    """가용 잔액 전체의 레버리지 명목가치를 계약 수량 단위로 내림합니다."""
    available = Decimal(str(available_usdt))
    price = Decimal(str(entry_price))
    step = Decimal(str(size_step))
    minimum = Decimal(str(minimum_size))
    leverage_value = Decimal(str(leverage))

    if available <= 0:
        raise ValueError("사용 가능한 USDT 잔액이 없습니다")
    if price <= 0:
        raise ValueError("진입가가 올바르지 않습니다")
    if leverage_value <= 0:
        raise ValueError("레버리지가 올바르지 않습니다")
    if step <= 0:
        raise ValueError("계약 수량 단위가 올바르지 않습니다")

    raw_size = available * leverage_value / price
    units = (raw_size / step).to_integral_value(rounding=ROUND_DOWN)
    size = units * step
    if size < minimum:
        raise ValueError(
            f"계산된 주문 수량 {size} BTC가 최소 주문 수량 {minimum} BTC보다 작습니다"
        )

    decimals = max(0, -step.normalize().as_tuple().exponent)
    return f"{size:.{decimals}f}"
