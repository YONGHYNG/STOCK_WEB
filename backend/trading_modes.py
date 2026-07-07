# 역할: 실거래와 모의거래 모드를 구분하는 설정 파일.
"""
매매 모드 및 주문 상태 열거형

TradingMode:
  SIGNAL_ONLY   - 신호만 분석, 주문 없음 (기본값)
  PAPER_TRADING - 모의매매 (DB 기록, 실제 주문 없음)
  LIVE_TRADING  - 실거래 (Bitget 실제 주문)

OrderStatus:
  SIGNAL_ONLY      - 신호만 기록됨
  PAPER_OPEN       - 모의 포지션 오픈
  PAPER_CLOSED     - 모의 포지션 청산
  ORDER_REQUESTED  - 실제 주문 요청됨
  ORDER_FILLED     - 실제 주문 체결됨
  ORDER_FAILED     - 주문 실패
  POSITION_CLOSED  - 포지션 청산 완료
"""

from enum import Enum


class TradingMode(str, Enum):
    SIGNAL_ONLY  = "SIGNAL_ONLY"
    PAPER_TRADING = "PAPER_TRADING"
    LIVE_TRADING  = "LIVE_TRADING"

    def label(self) -> str:
        return {
            TradingMode.SIGNAL_ONLY:   "신호 분석만",
            TradingMode.PAPER_TRADING: "모의매매",
            TradingMode.LIVE_TRADING:  "실거래",
        }[self]


class OrderStatus(str, Enum):
    SIGNAL_ONLY     = "SIGNAL_ONLY"
    PAPER_OPEN      = "PAPER_OPEN"
    PAPER_CLOSED    = "PAPER_CLOSED"
    ORDER_REQUESTED = "ORDER_REQUESTED"
    ORDER_FILLED    = "ORDER_FILLED"
    ORDER_FAILED    = "ORDER_FAILED"
    POSITION_CLOSED = "POSITION_CLOSED"
