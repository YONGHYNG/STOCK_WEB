# 역할: 매매 신호 산정과 진입 판단을 담당하는 서비스.
from backend.strategy.multi_timeframe_strategy import TradingAIEngine, TradingResult


class SignalService:
    def __init__(self, engine: TradingAIEngine | None = None):
        self.engine = engine or TradingAIEngine()

    def analyze(
        self,
        candles_by_timeframe: dict[str, list[dict]],
        all_time_high: float | None = None,
        all_time_low: float | None = None,
        market: dict | None = None,
        account_equity: float | None = None,
    ) -> TradingResult:
        return self.engine.analyze_multi_timeframe(
            candles_by_timeframe,
            all_time_high=all_time_high,
            all_time_low=all_time_low,
            market=market,
            account_equity=account_equity,
        )


__all__ = ["SignalService"]
