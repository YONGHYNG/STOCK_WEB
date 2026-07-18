"""매매 계획 알림 기능."""

from backend.notifications.gmail_notifier import gmail_is_configured, send_trade_plan_email

__all__ = ["gmail_is_configured", "send_trade_plan_email"]
