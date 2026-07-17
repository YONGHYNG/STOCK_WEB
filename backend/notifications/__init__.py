"""매매 계획 알림 기능."""

from backend.notifications.gmail_notifier import send_trade_plan_email

__all__ = ["send_trade_plan_email"]
