# 역할: 자동매매 진입 전 리스크 조건을 거는 파일.
"""
리스크 관리자 - 자동매매 진입 전 안전 조건 검사

check_entry() 가 (allowed: bool, reason: str) 를 반환합니다.
  allowed=True  → 진입 허용
  allowed=False → 진입 거부, reason에 이유 기록
"""

import time
from backend.risk.settings import RiskSettings
from backend.trading_modes import TradingMode
from backend.config import SYMBOL


class RiskManager:
    def __init__(self, settings: RiskSettings):
        self.settings = settings
        self._daily_pnl_pct: float = 0.0        # 당일 누적 손익률
        self._consecutive_losses: int = 0        # 연속 손실 횟수
        self._last_order_ts: float = 0.0         # 마지막 주문 타임스탬프
        self._emergency_stop: bool = False        # 긴급정지 여부
        self._daily_reset_date: str = ""          # 일일 리셋 날짜 기록

    # ── 외부에서 호출 ──────────────────────────────────────────────────────────

    def check_entry(
        self,
        direction: str,
        confidence: float,
        mode: TradingMode,
        cached_positions: list,
        private_client,
        entry_price: float | None = None,
        stop_loss: float | None = None,
        entry_grade: str | None = None,
        risk_warnings: list[str] | None = None,
    ) -> tuple[bool, str]:
        """
        자동매매 진입 가능 여부를 검사합니다.
        Returns:
            (True, "")          - 진입 허용
            (False, "거부이유")  - 진입 거부
        """
        self._maybe_reset_daily()
        s = self.settings

        # 1. 긴급정지
        if self._emergency_stop:
            return False, "[긴급정지] 자동매매 차단됨"

        # 2. 방향 확인
        if direction not in ("LONG", "SHORT"):
            return False, f"방향이 {direction}이므로 진입하지 않음"

        # 2-1. 선물 전용 진입 등급/위험 필터 확인
        if entry_grade in ("C", "D", "F"):
            return False, f"진입 등급 {entry_grade}이므로 자동 진입하지 않음"
        blocking_keywords = ("진입 금지", "진입 보류", "거리 부족", "기대 손익비", "기대수익", "충돌")
        for warning in risk_warnings or []:
            if any(key in warning for key in blocking_keywords):
                return False, f"위험 필터 발생: {warning}"

        # 3. 신뢰도 확인
        if confidence < s.confidence_threshold:
            return False, (
                f"신뢰도 {confidence:.1f}% < 임계값 {s.confidence_threshold:.0f}% "
                f"→ 진입 조건 미충족"
            )

        # 4. 모드 확인
        if mode == TradingMode.SIGNAL_ONLY:
            return False, "현재 모드가 SIGNAL_ONLY 이므로 주문하지 않음"

        # 5. LIVE_TRADING 시 실거래 허용 체크
        if mode == TradingMode.LIVE_TRADING:
            if private_client is None:
                return False, "API 키가 설정되지 않아 실거래 불가"
            if not s.live_trading_allowed:
                return False, "리스크 설정에서 실거래 허용이 비활성화되어 있음"

        # 6. 1회 최대 손실률 체크
        if entry_price and stop_loss:
            expected_loss_pct = abs(entry_price - stop_loss) / entry_price * 100
            if expected_loss_pct > s.max_loss_pct:
                return False, (
                    f"예상 손실률 {expected_loss_pct:.2f}% > "
                    f"1회 최대 손실률 {s.max_loss_pct:.2f}%"
                )

        # 7. 재진입 대기 시간
        elapsed = time.time() - self._last_order_ts
        if self._last_order_ts > 0 and elapsed < s.reentry_wait_seconds:
            remaining = int(s.reentry_wait_seconds - elapsed)
            return False, f"재진입 대기 중 ({remaining}초 남음)"

        # 8. 일일 손실 제한
        if self._daily_pnl_pct <= -abs(s.daily_max_loss_pct):
            return False, (
                f"일일 손실 한도 도달 ({self._daily_pnl_pct:.2f}% / "
                f"-{s.daily_max_loss_pct:.1f}%)"
            )

        # 9. 연속 손실 제한
        if self._consecutive_losses >= s.consecutive_loss_limit:
            return False, (
                f"연속 손실 {self._consecutive_losses}회 → "
                f"한도({s.consecutive_loss_limit}회) 도달, 자동매매 중단"
            )

        # 10. 거래소 포지션 체크 (cached_positions 기준)
        btc_positions = [p for p in cached_positions if p.get("symbol") == SYMBOL]
        if btc_positions:
            existing_side = btc_positions[0].get("holdSide", "").upper()
            if existing_side == direction:
                return False, f"이미 {direction} 포지션 보유 중, 추가 진입하지 않음"
            # 반대 포지션 → 청산 후 반전 (호출자에서 처리)
            return True, f"반대 {existing_side} 포지션 있음, 청산 후 {direction} 진입"

        return True, ""

    def record_trade_result(self, pnl_pct: float):
        """거래 결과를 기록합니다."""
        self._daily_pnl_pct += pnl_pct
        if pnl_pct < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0
        self._last_order_ts = time.time()

    def record_order_placed(self):
        """주문 발행 시각만 기록 (아직 체결 전)."""
        self._last_order_ts = time.time()

    def activate_emergency_stop(self):
        self._emergency_stop = True

    def deactivate_emergency_stop(self):
        self._emergency_stop = False

    @property
    def is_emergency_stopped(self) -> bool:
        return self._emergency_stop

    @property
    def daily_pnl_pct(self) -> float:
        return self._daily_pnl_pct

    @property
    def consecutive_losses(self) -> int:
        return self._consecutive_losses

    # ── Internal ───────────────────────────────────────────────────────────────

    def _maybe_reset_daily(self):
        from datetime import date
        today = str(date.today())
        if today != self._daily_reset_date:
            self._daily_pnl_pct = 0.0
            self._consecutive_losses = 0
            self._daily_reset_date = today
