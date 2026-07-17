"""Gmail SMTP를 이용해 확정된 다음 포지션 계획을 이메일로 알립니다."""

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


DEFAULT_RECIPIENT = "a01025932320@gmail.com"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "gmail_config.json"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def load_gmail_config() -> tuple[str, str, str]:
    sender = os.getenv("TRADE_EMAIL_SENDER", "").strip()
    app_password = os.getenv("TRADE_EMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    recipient = os.getenv("TRADE_EMAIL_RECIPIENT", DEFAULT_RECIPIENT).strip()
    if sender and app_password:
        return sender, app_password, recipient
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return (
            sender or str(data.get("sender") or "").strip(),
            app_password or str(data.get("app_password") or "").replace(" ", "").strip(),
            recipient or str(data.get("recipient") or DEFAULT_RECIPIENT).strip(),
        )
    except (OSError, ValueError, TypeError):
        return sender, app_password, recipient


def save_gmail_config(sender: str, app_password: str, recipient: str = DEFAULT_RECIPIENT) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(
            {"sender": sender.strip(), "app_password": app_password.replace(" ", "").strip(), "recipient": recipient.strip()},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _send_message(sender: str, app_password: str, recipient: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ssl.create_default_context(), timeout=15) as smtp:
        smtp.login(sender, app_password)
        smtp.send_message(message)


def send_test_email(sender: str, app_password: str, recipient: str = DEFAULT_RECIPIENT) -> None:
    _send_message(
        sender,
        app_password,
        recipient,
        "[BTCUSDT] Gmail 알림 연결 완료",
        "BTCUSDT 다음 포지션 Gmail 알림 연결이 완료되었습니다.",
    )


def send_trade_plan_email(result: dict) -> tuple[bool, str]:
    sender, app_password, recipient = load_gmail_config()
    if not sender or not app_password:
        return False, "Gmail 설정이 없음 (python -m backend.notifications.gmail_setup 실행 필요)"

    direction = str(result.get("direction") or "HOLD")
    entry = float(result.get("entry_price") or 0)
    stop = float(result.get("stop_loss") or 0)
    tp1 = float(result.get("take_profit_1") or 0)
    tp2 = float(result.get("take_profit_2") or 0)
    if direction not in ("LONG", "SHORT") or not all((entry, stop, tp1, tp2)):
        return False, "포지션 또는 진입·손절·익절 가격이 완성되지 않음"

    body = (
        "BTCUSDT 포지션 지정가가 체결되었습니다.\n\n"
        f"방향: {direction}\n"
        f"진입 지정가: {entry:,.2f} USDT\n"
        f"손절가: {stop:,.2f} USDT\n"
        f"1차 익절가: {tp1:,.2f} USDT\n"
        f"2차 익절가: {tp2:,.2f} USDT\n"
    )
    _send_message(sender, app_password, recipient, f"[BTCUSDT] {direction} 포지션 체결", body)
    return True, recipient
