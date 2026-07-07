# 역할: 전략 조건을 과거 데이터로 검증하는 백테스트 도구.
"""
백테스터 - 저장된 캔들 데이터를 기반으로 단순 시뮬레이션을 수행합니다.

사용법:
    from backend.strategy.backtester import Backtester, BacktestConfig, BacktestResult
    cfg = BacktestConfig(start_ts=..., end_ts=..., timeframe="1H",
                         initial_capital=10000, fee_rate=0.0005, slippage=0.0002)
    result = Backtester().run(cfg)

알고리즘:
  - 현재 운영 엔진(`TradingAIEngine`)과 동일한 선물 단타 판단 기준 사용
  - 5m/15m/30m 중심 시장 모드, 점수, 등급, 리스크 필터를 통과한 A/B 신호만 진입
  - SL/TP는 운영 엔진이 반환한 ATR 기반 가격 사용
  - 시뮬레이션은 캔들 단위(오픈/하이/로우/클로즈 순)로 TP/SL 체크
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from backend.database import get_candles_between
from backend.config import SYMBOL
from backend.strategy.multi_timeframe_strategy import TradingAIEngine


# ── 설정 ────────────────────────────────────────────────────────────────────

@dataclass
class BacktestConfig:
    start_ts: int            # 시작 타임스탬프 (ms)
    end_ts: int              # 종료 타임스탬프 (ms)
    timeframe: str = "1H"
    initial_capital: float = 10_000.0
    fee_rate: float = 0.0005   # 편도 수수료
    slippage: float = 0.0002   # 슬리피지
    order_size_pct: float = 10.0   # 자본 대비 주문 비율 (%)


# ── 결과 ────────────────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    total_trades: int = 0
    win_trades:   int = 0
    loss_trades:  int = 0
    tp_trades:    int = 0
    sl_trades:    int = 0

    cumulative_return_pct: float = 0.0
    avg_win_pct:           float = 0.0
    avg_loss_pct:          float = 0.0
    max_drawdown_pct:      float = 0.0
    profit_factor:         float = 0.0
    final_capital:         float = 0.0

    trade_log: list[dict] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        if self.total_trades == 0:
            return 0.0
        return self.win_trades / self.total_trades * 100

    def to_dict(self) -> dict:
        return {
            "total_trades":          self.total_trades,
            "win_trades":            self.win_trades,
            "loss_trades":           self.loss_trades,
            "tp_trades":             self.tp_trades,
            "sl_trades":             self.sl_trades,
            "win_rate":              round(self.win_rate, 2),
            "cumulative_return_pct": round(self.cumulative_return_pct, 2),
            "avg_win_pct":           round(self.avg_win_pct, 4),
            "avg_loss_pct":          round(self.avg_loss_pct, 4),
            "max_drawdown_pct":      round(self.max_drawdown_pct, 2),
            "profit_factor":         round(self.profit_factor, 2),
            "final_capital":         round(self.final_capital, 2),
        }


# ── 백테스터 ────────────────────────────────────────────────────────────────

class Backtester:

    def run(self, cfg: BacktestConfig) -> BacktestResult:
        """백테스트를 실행하고 결과를 반환합니다."""
        candles = self._load_candles(cfg)
        if len(candles) < 80:
            r = BacktestResult()
            r.final_capital = cfg.initial_capital
            return r

        highs   = [c["high"]  for c in candles]
        lows    = [c["low"]   for c in candles]
        opens   = [c["open"]  for c in candles]

        capital     = cfg.initial_capital
        peak_cap    = capital
        max_dd      = 0.0
        position    = None   # None | {direction, entry, sl, tp1, tp2}
        win_pcts:  list[float] = []
        loss_pcts: list[float] = []
        trade_log: list[dict]  = []
        tp_count   = 0
        sl_count   = 0
        engine = TradingAIEngine()

        start = 80

        for i in range(start, len(candles)):
            c = candles[i]
            ts    = c["timestamp"]
            o, h, l, cl = opens[i], highs[i], lows[i], c["close"]

            # TP/SL 체크 (현재 캔들 내에서)
            if position:
                result_code, exit_px = self._check_tpsl(position, o, h, l, cl)
                if result_code:
                    pnl = self._calc_pnl(position, exit_px, cfg)
                    capital   += capital * cfg.order_size_pct / 100 * pnl / 100
                    peak_cap   = max(peak_cap, capital)
                    dd         = (peak_cap - capital) / peak_cap * 100
                    max_dd     = max(max_dd, dd)
                    if pnl >= 0:
                        win_pcts.append(pnl)
                        tp_count += 1
                    else:
                        loss_pcts.append(pnl)
                        sl_count += 1
                    trade_log.append({
                        "entry_ts":  position["ts"],
                        "exit_ts":   ts,
                        "direction": position["direction"],
                        "entry_px":  position["entry"],
                        "exit_px":   exit_px,
                        "result":    result_code,
                        "pnl_pct":   round(pnl, 3),
                    })
                    position = None

            # 새 진입 시그널
            if position is None:
                market = self._synthetic_market(cl, cfg.slippage)
                frames = self._build_backtest_frames(candles[: i + 1])
                signal = engine.analyze_multi_timeframe(frames, market=market, account_equity=cfg.initial_capital).to_dict()
                direction = signal.get("direction")
                if direction in ("LONG", "SHORT") and signal.get("entry_grade") in ("A", "B"):
                    entry = signal["entry_price"]
                    sl = signal.get("stop_loss")
                    tp1 = signal.get("take_profit_1")
                    tp2 = signal.get("take_profit_2")
                    if not sl or not tp1 or not tp2:
                        continue
                    position = {
                        "direction": direction,
                        "entry": entry, "sl": sl, "tp1": tp1, "tp2": tp2,
                        "ts": ts,
                    }

        # 미청산 포지션 강제 청산
        if position and len(candles) > 0:
            last = candles[-1]
            exit_px = last["close"]
            pnl     = self._calc_pnl(position, exit_px, cfg)
            capital += capital * cfg.order_size_pct / 100 * pnl / 100
            trade_log.append({
                "entry_ts":  position["ts"],
                "exit_ts":   last["timestamp"],
                "direction": position["direction"],
                "entry_px":  position["entry"],
                "exit_px":   exit_px,
                "result":    "FORCED_CLOSE",
                "pnl_pct":   round(pnl, 3),
            })

        total  = len(trade_log)
        wins   = len(win_pcts)
        losses = len(loss_pcts)
        gross_profit = sum(p for p in win_pcts)  if win_pcts  else 0.0
        gross_loss   = sum(abs(p) for p in loss_pcts) if loss_pcts else 0.0

        result = BacktestResult(
            total_trades           = total,
            win_trades             = wins,
            loss_trades            = losses,
            tp_trades              = tp_count,
            sl_trades              = sl_count,
            cumulative_return_pct  = (capital - cfg.initial_capital) / cfg.initial_capital * 100,
            avg_win_pct            = gross_profit / wins   if wins   else 0.0,
            avg_loss_pct           = -(gross_loss  / losses) if losses else 0.0,
            max_drawdown_pct       = max_dd,
            profit_factor          = gross_profit / gross_loss if gross_loss > 0 else float("inf"),
            final_capital          = capital,
            trade_log              = trade_log,
        )
        return result

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _load_candles(self, cfg: BacktestConfig) -> list[dict]:
        return get_candles_between(SYMBOL, cfg.timeframe, cfg.start_ts, cfg.end_ts)

    @staticmethod
    def _build_backtest_frames(candles: list[dict]) -> dict[str, list[dict]]:
        # 단일 시간봉 백테스트 데이터만 있을 때도 운영 엔진의 동일한 기준을 사용한다.
        return {tf: candles for tf in ("5m", "15m", "30m", "1H", "6H", "1D")}

    @staticmethod
    def _synthetic_market(close: float, slippage: float) -> dict:
        spread = max(slippage, 0.0001)
        return {
            "last_price": close,
            "mark_price": close,
            "index_price": close,
            "best_bid": close * (1 - spread / 2),
            "best_ask": close * (1 + spread / 2),
            "funding_rate": 0.0,
        }

    @staticmethod
    def _check_tpsl(
        pos: dict, o: float, h: float, l: float, cl: float
    ) -> tuple[Optional[str], float]:
        """캔들 내에서 TP/SL 체크. (result_code, exit_price)"""
        d   = pos["direction"]
        sl  = pos["sl"]
        tp1 = pos["tp1"]
        tp2 = pos["tp2"]
        if d == "LONG":
            if h >= tp2: return "TP2", tp2
            if h >= tp1: return "TP1", tp1
            if l <= sl:  return "SL",  sl
        else:
            if l <= tp2: return "TP2", tp2
            if l <= tp1: return "TP1", tp1
            if h >= sl:  return "SL",  sl
        return None, 0.0

    @staticmethod
    def _calc_pnl(pos: dict, exit_px: float, cfg: BacktestConfig) -> float:
        """수수료·슬리피지 포함 손익률 (%)."""
        entry = pos["entry"]
        if pos["direction"] == "LONG":
            gross = (exit_px - entry) / entry * 100
        else:
            gross = (entry - exit_px) / entry * 100
        cost = (cfg.fee_rate + cfg.slippage) * 2 * 100
        return gross - cost
