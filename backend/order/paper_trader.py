# 역할: 실주문 없이 모의 매매 체결을 처리하는 파일.
"""
모의매매 (Paper Trading)

실제 Bitget 주문 없이 trades 테이블에 trade_type='PAPER' 로 기록합니다.
기존 database.open_trade / close_trade 를 재사용합니다.
"""

from __future__ import annotations

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
            size_btc      = r.get("position_size_btc"),
            position_size_percent = float(r.get("position_size_percent") or 100),
            entry_stage   = int(r.get("entry_stage") or 2),
        )
        self._open_id   = trade_id
        self._open_data = {
            "direction": direction,
            "entry":     entry,
            "sl":        r.get("stop_loss"),
            "tp1":       r.get("take_profit_1"),
            "tp2":       r.get("take_profit_2"),
            "size":      r.get("position_size_btc"),
            "initial_size": r.get("position_size_btc"),
            "remaining_size": r.get("position_size_btc"),
            "partial_realized_pnl": 0.0,
            "tp1_taken": False,
            "tp2_taken": False,
            "position_size_percent": float(r.get("position_size_percent") or 100),
            "entry_stage": int(r.get("entry_stage") or 2),
            "max_favorable_move": 0.0,
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
        leg_pnl_pct = _net_pnl_pct(t["direction"], entry, exit_price, exit_fee_rate)
        remaining_size = float(t.get("remaining_size") if t.get("remaining_size") is not None else t.get("size") or 0)
        partial_realized = float(t.get("partial_realized_pnl") or 0)
        final_leg_amount = remaining_size * entry * (leg_pnl_pct / 100)
        realized_amount = partial_realized + final_leg_amount
        initial_size = float(t.get("initial_size") or t.get("size") or 0)
        initial_notional = initial_size * entry
        pnl_pct = (realized_amount / initial_notional * 100) if initial_notional > 0 else leg_pnl_pct
        tid = self._open_id
        db.close_trade(
            trade_id      = tid,
            exit_price    = exit_price,
            result        = result,
            pnl_pct       = pnl_pct,
            profit_reason = profit_reason,
            loss_reason   = loss_reason,
            realized_pnl_amount = round(realized_amount, 8),
        )
        self._open_id   = None
        self._open_data = None
        return tid, pnl_pct

    def take_partial(self, exit_price: float, result_code: str, share_of_initial: float = 0.35) -> tuple[int, float, float]:
        """TP1/TP2에서 최초 체결 수량의 일부를 청산한다."""
        if not self._open_id or not self._open_data:
            return 0, 0.0, 0.0
        t = self._open_data
        initial_size = float(t.get("initial_size") or t.get("size") or 0)
        remaining = float(t.get("remaining_size") if t.get("remaining_size") is not None else t.get("size") or 0)
        quantity = min(remaining, initial_size * max(0.0, float(share_of_initial)))
        if quantity <= 0:
            return self._open_id, 0.0, remaining
        pnl_pct = _net_pnl_pct(t["direction"], float(t["entry"]), float(exit_price))
        amount = quantity * float(t["entry"]) * (pnl_pct / 100)
        remaining = max(0.0, remaining - quantity)
        t["remaining_size"] = remaining
        t["partial_realized_pnl"] = float(t.get("partial_realized_pnl") or 0) + amount
        if result_code == "TP1":
            t["tp1_taken"] = True
            # 1R 도달 후 남은 물량의 손절을 진입가로 올린다.
            t["sl"] = float(t["entry"])
        else:
            t["tp2_taken"] = True
            t["sl"] = float(t.get("tp1") or t["entry"])
        db.record_paper_partial_exit(self._open_id, remaining, amount, result_code, t.get("sl"))
        return self._open_id, amount, remaining

    def check_tp_sl(self, price: float) -> Optional[str]:
        """
        현재가가 TP/SL에 도달했으면 result_code 를 반환합니다.
        도달하지 않았으면 None.
        """
        if not self._open_data:
            return None
        t         = self._open_data
        direction = t["direction"]
        entry = float(t.get("entry") or 0)
        favorable_move = (
            float(price) - entry if direction == "LONG" else entry - float(price)
        )
        t["max_favorable_move"] = max(
            float(t.get("max_favorable_move") or 0), favorable_move
        )
        # 구조적 손절은 1차 50% 진입 순간부터 활성화한다.
        sl  = t.get("sl")
        tp1 = t.get("tp1")
        tp2 = t.get("tp2")

        if direction == "LONG":
            if tp1 and not t.get("tp1_taken") and price >= tp1: return "TP1_PARTIAL"
            if tp2 and t.get("tp1_taken") and not t.get("tp2_taken") and price >= tp2: return "TP2_PARTIAL"
            if sl  and price <= sl:    return "SL"
        elif direction == "SHORT":
            if tp1 and not t.get("tp1_taken") and price <= tp1: return "TP1_PARTIAL"
            if tp2 and t.get("tp1_taken") and not t.get("tp2_taken") and price <= tp2: return "TP2_PARTIAL"
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

    def update_open_size(self, size_btc: float) -> None:
        if not self._open_id or not self._open_data:
            return
        size = float(size_btc)
        db.update_trade_size(self._open_id, size)
        self._open_data["size"] = size

    def scale_in(self, fill_price: float, added_size: float, plan: dict) -> tuple[int, float]:
        """기존 PAPER 포지션에 추가 체결하고 평균단가와 보호가격을 갱신한다."""
        if not self._open_id or not self._open_data:
            return 0, 0.0
        current_size = float(self._open_data.get("size") or 0)
        added = float(added_size or 0)
        if current_size <= 0 or added <= 0:
            return self._open_id, float(self._open_data.get("entry") or 0)
        total_size = current_size + added
        average = (
            float(self._open_data["entry"]) * current_size + float(fill_price) * added
        ) / total_size
        db.update_paper_trade_position(
            self._open_id, average, total_size,
            plan.get("stop_loss"), plan.get("take_profit_1"), plan.get("take_profit_2"),
            float(plan.get("position_size_percent") or 100),
            int(plan.get("entry_stage") or 2),
        )
        self._open_data.update({
            "entry": average, "size": total_size,
            "initial_size": total_size,
            "remaining_size": total_size,
            "position_size_percent": float(plan.get("position_size_percent") or 100),
            "entry_stage": int(plan.get("entry_stage") or 2),
            "sl": plan.get("stop_loss"), "tp1": plan.get("take_profit_1"),
            "tp2": plan.get("take_profit_2"),
        })
        return self._open_id, average

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
                "size":      row.get("size_btc"),
                "initial_size": row.get("initial_size_btc") or row.get("size_btc"),
                "remaining_size": row.get("remaining_size_btc") if row.get("remaining_size_btc") is not None else row.get("size_btc"),
                "partial_realized_pnl": float(row.get("partial_realized_pnl_amount") or 0),
                "tp1_taken": bool(row.get("tp1_taken")),
                "tp2_taken": bool(row.get("tp2_taken")),
                "position_size_percent": float(row.get("position_size_percent") or 100),
                "entry_stage": int(row.get("entry_stage") or 2),
                "max_favorable_move": 0.0,
            }
