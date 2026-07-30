"""실거래 주문 수량 계산."""

from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from typing import Union

NumberLike = Union[int, float, str]


def full_balance_size(
    available_usdt: NumberLike,
    leverage: int,
    entry_price: NumberLike,
    size_step: NumberLike,
    minimum_size: NumberLike,
    minimum_notional: NumberLike = 0,
    fee_rate: NumberLike = 0,
    open_cost_up_ratio: NumberLike = 0,
    maximum_size: NumberLike = 0,
) -> str:
    """가용 잔액 전체의 레버리지 명목가치를 계약 수량 단위로 내림합니다."""
    available = Decimal(str(available_usdt))
    price = Decimal(str(entry_price))
    step = Decimal(str(size_step))
    minimum = Decimal(str(minimum_size))
    min_notional = Decimal(str(minimum_notional))
    fee = Decimal(str(fee_rate))
    cost_buffer = Decimal(str(open_cost_up_ratio))
    maximum = Decimal(str(maximum_size))
    leverage_value = Decimal(str(leverage))

    if available <= 0:
        raise ValueError("사용 가능한 USDT 잔액이 없습니다")
    if price <= 0:
        raise ValueError("진입가가 올바르지 않습니다")
    if leverage_value <= 0:
        raise ValueError("레버리지가 올바르지 않습니다")
    if step <= 0:
        raise ValueError("계약 수량 단위가 올바르지 않습니다")

    # 증거금 외에 진입 수수료와 거래소 개시비용 가산분까지 같은 잔액에서
    # 지불할 수 있도록 전액 사용 가능한 최대 명목가치를 역산합니다.
    denominator = Decimal("1") + leverage_value * fee + cost_buffer
    raw_size = available * leverage_value / denominator / price
    units = (raw_size / step).to_integral_value(rounding=ROUND_DOWN)
    size = units * step
    if maximum > 0:
        size = min(size, maximum)
        size = (size / step).to_integral_value(rounding=ROUND_DOWN) * step
    if size < minimum:
        raise ValueError(
            f"계산된 주문 수량 {size} BTC가 최소 주문 수량 {minimum} BTC보다 작습니다"
        )
    if size * price < min_notional:
        raise ValueError(
            f"주문 명목금액 {size * price} USDT가 최소 금액 "
            f"{min_notional} USDT보다 작습니다"
        )

    decimals = max(0, -step.normalize().as_tuple().exponent)
    return f"{size:.{decimals}f}"


def normalize_limit_price(
    price: NumberLike,
    price_place: NumberLike,
    price_end_step: NumberLike,
    side: str,
) -> str:
    """거래소 가격 단위로 매수는 내림, 매도는 올림 처리합니다."""
    value = Decimal(str(price))
    places = int(price_place)
    end_step = Decimal(str(price_end_step))
    tick = end_step * (Decimal("10") ** -places)
    if value <= 0 or tick <= 0:
        raise ValueError("주문 가격 또는 가격 단위가 올바르지 않습니다")
    rounding = ROUND_DOWN if side.lower() == "buy" else ROUND_CEILING
    units = (value / tick).to_integral_value(rounding=rounding)
    normalized = units * tick
    return f"{normalized:.{places}f}"


def entry_price_deviation_pct(planned_price: NumberLike, latest_price: NumberLike) -> float:
    planned = Decimal(str(planned_price))
    latest = Decimal(str(latest_price))
    if planned <= 0 or latest <= 0:
        raise ValueError("계획 진입가 또는 최신 가격이 올바르지 않습니다")
    return float(abs(latest - planned) / planned * Decimal("100"))
