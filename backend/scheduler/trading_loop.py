class TradingLoop:
    def __init__(self, signal_service):
        self.signal_service = signal_service

    def analyze_once(self, candles_by_timeframe: dict[str, list[dict]], **kwargs):
        return self.signal_service.analyze(candles_by_timeframe, **kwargs)


__all__ = ["TradingLoop"]
