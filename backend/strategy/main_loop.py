# 역할: 1분 확정 캔들 기준으로 지표, 전략, 리스크, 주문을 순서대로 실행합니다.
import asyncio
import logging
from dataclasses import asdict

from backend.market.candle_collector import CandleCollector
from backend.order.order_manager import OrderManager
from backend.risk.risk_manager import StrategyRiskManager
from backend.strategy.indicator import add_indicators
from backend.strategy.strategy import VolumeTrendRsiStrategy
from backend.strategy.volume_trend_engine import TradingAIEngine


logger = logging.getLogger("volume_trend_strategy")


class MainLoop:
    def __init__(
        self,
        candle_collector: CandleCollector,
        strategy: VolumeTrendRsiStrategy | None = None,
        risk_manager: StrategyRiskManager | None = None,
        order_manager: OrderManager | None = None,
        timeframe: str = "1m",
        limit: int = 260,
    ):
        self.candle_collector = candle_collector
        self.strategy = strategy or VolumeTrendRsiStrategy()
        self.risk_manager = risk_manager or StrategyRiskManager()
        self.order_manager = order_manager or OrderManager(paper_trading=True)
        self.timeframe = timeframe
        self.limit = limit
        self.running = False

    async def run_forever(self) -> None:
        self.running = True
        while self.running:
            await self.run_once()
            await asyncio.sleep(60)

    async def run_once(self) -> dict:
        try:
            candles = self.candle_collector.fetch_recent(self.timeframe, self.limit)
            self.risk_manager.reset_api_errors()
        except Exception as exc:
            self.risk_manager.record_api_error()
            logger.exception("캔들 수집 실패: %s", exc)
            return {"ok": False, "error": str(exc)}

        # 마지막 원소는 확정 캔들이라고 가정한다. 실시간 미확정 캔들은 collector 단계에서 제외해야 한다.
        df = add_indicators(candles)
        decision = self.strategy.evaluate(df)
        result = {"decision": asdict(decision), "order": None}
        logger.info("signal=%s direction=%s reasons=%s", decision.signal, decision.direction, decision.reasons)

        if decision.direction not in ("LONG", "SHORT"):
            return result

        entry = decision.entry_price
        atr = float(df.iloc[-1].get("atr14") or 0)
        stop_loss = TradingAIEngine._risk_prices(decision.direction, entry, atr, df, decision, df.iloc[-1])[0]
        if stop_loss is None:
            result["risk_block"] = "손절가 계산 불가"
            return result

        allowed, reason, size = self.risk_manager.can_enter(decision.direction, entry, stop_loss, len(df) - 1)
        if not allowed:
            logger.info("entry blocked: %s", reason)
            result["risk_block"] = reason
            return result

        signal_payload = {**asdict(decision), "stop_loss": stop_loss}
        if decision.direction == "LONG":
            order = self.order_manager.place_long(size, entry, signal_payload)
        else:
            order = self.order_manager.place_short(size, entry, signal_payload)
        result["order"] = asdict(order)
        logger.info("order=%s", result["order"])
        return result

    def stop(self) -> None:
        self.running = False


__all__ = ["MainLoop"]
