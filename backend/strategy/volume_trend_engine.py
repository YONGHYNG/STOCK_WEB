# 역할: 거래량, 추세, RSI 전략을 기존 GUI/API 결과 형식으로 변환합니다.
from dataclasses import dataclass
from typing import Optional

from backend.config import SYMBOL, TAKER_FEE_RATE
from backend.strategy.indicator import add_indicators
from backend.strategy.strategy import VolumeTrendRsiStrategy


@dataclass
class TradingResult:
    timestamp: int
    entry_price: float
    direction: str
    long_probability: float
    short_probability: float
    confidence: float
    stop_loss: Optional[float]
    take_profit_1: Optional[float]
    take_profit_2: Optional[float]
    risk_reward_ratio: Optional[float]
    all_time_high_mode: bool
    all_time_low_mode: bool
    timeframe_directions: dict[str, str]
    reasons: list[str]
    analysis_price: float = 0.0
    last_price: Optional[float] = None
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    expected_entry_long: Optional[float] = None
    expected_entry_short: Optional[float] = None
    take_profit_3: Optional[float] = None
    long_score: float = 50.0
    short_score: float = 50.0
    entry_grade: str = "F"
    risk_warnings: Optional[list[str]] = None
    spread_rate: Optional[float] = None
    funding_rate: Optional[float] = None
    estimated_fee: Optional[float] = None
    estimated_funding_fee: Optional[float] = None
    net_risk_reward: Optional[float] = None
    position_size_btc: Optional[float] = None
    position_value: Optional[float] = None
    max_loss_usdt: Optional[float] = None
    leverage: int = 3
    liquidation_price: Optional[float] = None
    liquidation_gap: Optional[float] = None
    stop_gap: Optional[float] = None
    market_mode: str = "HOLD"
    position_size_ratio: float = 1.0
    timeframe_summary: Optional[dict[str, dict]] = None
    strategy_signal: str = "HOLD"

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["risk_warnings"] = d.get("risk_warnings") or []
        d["warnings"] = d["risk_warnings"]
        d["symbol"] = SYMBOL
        d["timeframe_summary"] = d.get("timeframe_summary") or {}
        return d


class TradingAIEngine:
    def __init__(self) -> None:
        self.strategy = VolumeTrendRsiStrategy()

    def analyze(
        self,
        candles: list[dict],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
        market: Optional[dict] = None,
        account_equity: Optional[float] = None,
    ) -> TradingResult:
        return self.analyze_multi_timeframe(
            {"5m": candles},
            all_time_high=all_time_high,
            all_time_low=all_time_low,
            market=market,
            account_equity=account_equity,
        )

    def analyze_multi_timeframe(
        self,
        candles_by_timeframe: dict[str, list[dict]],
        all_time_high: Optional[float] = None,
        all_time_low: Optional[float] = None,
        market: Optional[dict] = None,
        account_equity: Optional[float] = None,
    ) -> TradingResult:
        candles = candles_by_timeframe.get("1m") or candles_by_timeframe.get("5m") or []
        market = market or {}
        df = add_indicators(candles)
        if len(df) < 220:
            last_price = float(df.iloc[-1]["close"]) if len(df) else 0.0
            return self._empty(last_price, "MA200 기반 전략 계산을 위한 확정 캔들이 부족합니다.")

        decision = self.strategy.evaluate(df)
        last = df.iloc[-1]
        price = float(market.get("last_price") or decision.entry_price)
        pricing = self._pricing(price, market)
        direction = decision.direction
        entry = pricing["expected_entry_long"] if direction == "LONG" else pricing["expected_entry_short"] if direction == "SHORT" else price
        atr = float(last.get("atr14") or 0)
        stop_loss, tp1, tp2, rr = self._risk_prices(direction, entry, atr)
        warnings = list(decision.warnings)
        entry_grade = "B" if direction in ("LONG", "SHORT") and stop_loss and rr and rr >= 1.5 else "F"
        if decision.signal.startswith("WAIT"):
            entry_grade = "F"
            warnings.append("WAIT 상태: 시장가 추격 진입 금지")
        if entry_grade in ("C", "D", "F"):
            final_direction = "HOLD"
        else:
            final_direction = direction

        long_score = 75.0 if direction == "LONG" else 25.0 if direction == "SHORT" else 50.0
        short_score = 75.0 if direction == "SHORT" else 25.0 if direction == "LONG" else 50.0
        confidence = 100.0 if final_direction in ("LONG", "SHORT") else 0.0
        reasons = decision.reasons + [f"전략 신호: {decision.signal}", "모든 판단은 확정 캔들 기준"]
        if warnings:
            reasons += [f"경고: {w}" for w in warnings]

        value = None
        size = None
        fee = None
        if final_direction in ("LONG", "SHORT") and stop_loss:
            max_loss = float(account_equity or 1000.0) * 0.005
            risk_per_unit = abs(entry - stop_loss)
            size = max_loss / risk_per_unit if risk_per_unit > 0 else None
            value = size * entry if size else None
            fee = value * float(market.get("fee_rate") or TAKER_FEE_RATE) * 2 if value else None

        return TradingResult(
            timestamp=int(last.get("timestamp") or 0),
            entry_price=round(entry, 2),
            direction=final_direction,
            long_probability=long_score,
            short_probability=short_score,
            confidence=confidence,
            stop_loss=round(stop_loss, 2) if stop_loss else None,
            take_profit_1=round(tp1, 2) if tp1 else None,
            take_profit_2=round(tp2, 2) if tp2 else None,
            risk_reward_ratio=round(rr, 2) if rr else None,
            all_time_high_mode=bool(all_time_high and entry >= all_time_high),
            all_time_low_mode=bool(all_time_low and entry <= all_time_low),
            timeframe_directions={"1m": direction, "5m": direction},
            reasons=reasons,
            analysis_price=round(price, 2),
            last_price=pricing["last_price"],
            mark_price=pricing["mark_price"],
            index_price=pricing["index_price"],
            best_bid=pricing["best_bid"],
            best_ask=pricing["best_ask"],
            expected_entry_long=pricing["expected_entry_long"],
            expected_entry_short=pricing["expected_entry_short"],
            long_score=long_score,
            short_score=short_score,
            entry_grade=entry_grade,
            risk_warnings=warnings,
            spread_rate=pricing["spread_rate"],
            funding_rate=market.get("funding_rate"),
            estimated_fee=round(fee, 4) if fee else None,
            estimated_funding_fee=None,
            net_risk_reward=round(rr, 2) if rr else None,
            position_size_btc=round(size, 6) if size else None,
            position_value=round(value, 2) if value else None,
            max_loss_usdt=round(float(account_equity or 1000.0) * 0.005, 2),
            leverage=int(market.get("leverage") or 3),
            liquidation_price=market.get("liquidation_price"),
            stop_gap=round(abs(entry - stop_loss) / entry, 4) if stop_loss and entry else None,
            market_mode=decision.state,
            timeframe_summary={"1m": self._summary(last, decision), "5m": self._summary(last, decision)},
            strategy_signal=decision.signal,
        )

    @staticmethod
    def _pricing(price: float, market: dict) -> dict:
        bid = float(market.get("best_bid") or price * 0.99995)
        ask = float(market.get("best_ask") or price * 1.00005)
        mid = (bid + ask) / 2
        return {
            "last_price": round(price, 2),
            "mark_price": round(float(market.get("mark_price") or price), 2),
            "index_price": round(float(market.get("index_price") or market.get("mark_price") or price), 2),
            "best_bid": round(bid, 2),
            "best_ask": round(ask, 2),
            "expected_entry_long": round(ask, 2),
            "expected_entry_short": round(bid, 2),
            "spread_rate": (ask - bid) / mid if mid > 0 else None,
        }

    @staticmethod
    def _risk_prices(direction: str, entry: float, atr: float) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        if direction not in ("LONG", "SHORT") or atr <= 0:
            return None, None, None, None
        risk = atr * 1.2
        if direction == "LONG":
            stop = entry - risk
            return stop, entry + risk, entry + risk * 1.5, 1.5
        stop = entry + risk
        return stop, entry - risk, entry - risk * 1.5, 1.5

    @staticmethod
    def _summary(last, decision) -> dict:
        return {
            "direction": decision.direction,
            "signal": decision.signal,
            "close": float(last.get("close") or 0),
            "ma90": float(last.get("ma90") or 0),
            "ma200": float(last.get("ma200") or 0),
            "rsi14": float(last.get("rsi14") or 0),
            "atr14": float(last.get("atr14") or 0),
            "volume_ratio": float(last.get("volume_ratio") or 0),
            "support_level": decision.support_level,
            "breakout_level": decision.breakout_level,
        }

    @staticmethod
    def _empty(last_price: float, reason: str) -> TradingResult:
        return TradingResult(
            timestamp=0,
            entry_price=round(last_price, 2),
            direction="HOLD",
            long_probability=50.0,
            short_probability=50.0,
            confidence=0.0,
            stop_loss=None,
            take_profit_1=None,
            take_profit_2=None,
            risk_reward_ratio=None,
            all_time_high_mode=False,
            all_time_low_mode=False,
            timeframe_directions={},
            reasons=[reason],
            analysis_price=round(last_price, 2),
            last_price=round(last_price, 2),
            long_score=50.0,
            short_score=50.0,
            entry_grade="F",
            risk_warnings=["데이터 부족"],
            market_mode="HOLD",
            strategy_signal="HOLD",
        )

    def _calc_risk_prices(self, direction: str, entry: float, candles: list[dict]) -> tuple:
        df = add_indicators(candles)
        atr = float(df.iloc[-1].get("atr14") or 0) if len(df) else 0.0
        return self._risk_prices(direction, entry, atr)[:3] + (None,)


__all__ = ["TradingAIEngine", "TradingResult"]
