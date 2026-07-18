# 역할: 실주문 없이 모의 매매 체결을 처리하는 파일.
"""
모의매매 (Paper Trading)

실제 Bitget 주문 없이 trades 테이블에 trade_type='PAPER' 로 기록합니다.
기존 database.open_trade / close_trade 를 재사용합니다.
"""

from typing import Optional
import backend.database as db
from backend.config import MAKER_FEE_RATE, SYMBOL, TAKER_FEE_RATE


def _net_pnl_pct(direction: str, entry: float, exit_price: float, exit_fee_rate: float = MAKER_FEE_RATE) -> float:
    gross = (
        (exit_price - entry) / entry * 100
        if direction == "LONG"
        else (entry - exit_price) / entry * 100
    )
    return gross - (float(MAKER_FEE_RATE) + float(exit_fee_rate)) * 100


class PaperTrader:
    """
    모의매매 진입/청산/TP-SL 감시를 담당합니다.
    실제 주문은 전혀 보내지 않습니다.
    """

    def __init__(self):
        self._open_id:   int | None  = None
        self._open_data: dict | None = None   # {direction, entry, sl, tp1, tp2}

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def is_open(self) -> bool:
        return self._open_id is not None

    @property
    def open_data(self) -> dict | None:
        return self._open_data

    @property
    def open_id(self) -> int | None:
        return self._open_id

    # ── Trade lifecycle ─────────────────────────────────────────────────────────

    def open_trade(self, direction: str, r: dict) -> int:
        """
        모의 포지션을 DB에 기록합니다.
        Returns: trade_id
        """
        entry   = r.get("entry_price") or 0.0
        reasons = "\n".join(r.get("reasons", []))
        trade_id = db.open_trade(
            symbol        = SYMBOL,
            direction     = direction,
            entry_price   = entry,
            stop_loss     = r.get("stop_loss"),
            take_profit_1 = r.get("take_profit_1"),
            take_profit_2 = r.get("take_profit_2"),
            risk_reward   = r.get("risk_reward_ratio"),
            confidence    = r.get("confidence", 0),
            long_prob     = r.get("long_probability", 50),
            short_prob    = r.get("short_probability", 50),
            tf_directions = r.get("timeframe_directions", {}),
            entry_reason  = reasons,
            trade_type    = "PAPER",
        )
        self._open_id   = trade_id
        self._open_data = {
            "direction": direction,
            "entry":     entry,
            "sl":        r.get("stop_loss"),
            "tp1":       r.get("take_profit_1"),
            "tp2":       r.get("take_profit_2"),
        }
        return trade_id

    def close_trade(
        self,
        exit_price: float,
        result: str,
        profit_reason: str = "",
        loss_reason:   str = "",
        exit_fee_rate: float = MAKER_FEE_RATE,
    ) -> tuple[int, float]:
        """
        모의 포지션을 청산하고 (trade_id, pnl_pct)를 반환합니다.
        """
        if not self._open_id or not self._open_data:
            return 0, 0.0
        t     = self._open_data
        entry = t["entry"]
        pnl_pct = _net_pnl_pct(t["direction"], entry, exit_price, exit_fee_rate)
        tid = self._open_id
        db.close_trade(
            trade_id      = tid,
            exit_price    = exit_price,
            result        = result,
            pnl_pct       = pnl_pct,
            profit_reason = profit_reason,
            loss_reason   = loss_reason,
        )
        self._open_id   = None
        self._open_data = None
        return tid, pnl_pct

    def check_tp_sl(self, price: float) -> Optional[str]:
        """
        현재가가 TP/SL에 도달했으면 result_code 를 반환합니다.
        도달하지 않았으면 None.
        """
        if not self._open_data:
            return None
        t         = self._open_data
        direction = t["direction"]
        sl  = t.get("sl")
        tp1 = t.get("tp1")
        tp2 = t.get("tp2")

        if direction == "LONG":
            if tp2 and price >= tp2:   return "TP2"
            if tp1 and price >= tp1:   return "TP1"
            if sl  and price <= sl:    return "SL"
        elif direction == "SHORT":
            if tp2 and price <= tp2:   return "TP2"
            if tp1 and price <= tp1:   return "TP1"
            if sl  and price >= sl:    return "SL"
        return None

    def force_close(self, exit_price: float) -> tuple[int, float]:
        """시그널 반전 등으로 강제 청산합니다."""
        if not self._open_data:
            return 0, 0.0
        t = self._open_data
        entry = t["entry"]
        pnl_pct = _net_pnl_pct(t["direction"], entry, exit_price, TAKER_FEE_RATE)
        msg = (
            f"[모의매매 시그널변경] ${entry:,.2f} → ${exit_price:,.2f}  "
            f"({'+' if pnl_pct >= 0 else ''}{pnl_pct:.2f}%)"
        )
        return self.close_trade(
            exit_price    = exit_price,
            result        = "SIGNAL_CHANGE",
            profit_reason = msg if pnl_pct >= 0 else "",
            loss_reason   = msg if pnl_pct < 0  else "",
            exit_fee_rate = TAKER_FEE_RATE,
        )

    def restore_from_db(self):
        """프로그램 재시작 시 PAPER_OPEN 상태의 거래를 복구합니다."""
        row = db.get_open_trade(SYMBOL, trade_type="PAPER")
        if row:
            self._open_id   = row["id"]
            self._open_data = {
                "direction": row["direction"],
                "entry":     row["entry_price"],
                "sl":        row["stop_loss"],
                "tp1":       row["take_profit_1"],
                "tp2":       row["take_profit_2"],
            }
