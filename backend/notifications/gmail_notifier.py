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


def gmail_is_configured() -> bool:
    sender, app_password, recipient = load_gmail_config()
    return bool(sender and app_password and recipient)


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
    return send_trade_event_email("ENTRY", result)


def send_trade_event_email(event: str, result: dict) -> tuple[bool, str]:
    sender, app_password, recipient = load_gmail_config()
    if not sender or not app_password:
        return False, "Gmail 설정이 없음 (python -m backend.notifications.gmail_setup 실행 필요)"

    event = str(event or "").upper()
    direction = str(result.get("direction") or "HOLD")
    entry = float(result.get("entry_price") or 0)
    stop = float(result.get("stop_loss") or 0)
    tp1 = float(result.get("take_profit_1") or 0)
    tp2 = float(result.get("take_profit_2") or 0)
    exit_price = float(result.get("exit_price") or 0)
    pnl_pct = result.get("pnl_pct")
    mode = str(result.get("mode") or result.get("trade_type") or "").upper()
    if direction not in ("LONG", "SHORT") or not entry:
        return False, "포지션 방향 또는 진입 가격이 완성되지 않음"
    if event in ("PENDING", "ENTRY") and not all((stop, tp1, tp2)):
        return False, "포지션 또는 진입·손절·익절 가격이 완성되지 않음"

    mode_label = f"{mode} " if mode else ""
    price_lines = (
        f"방향: {direction}\n"
        f"진입 지정가: {entry:,.2f} USDT\n"
        f"손절가: {stop:,.2f} USDT\n"
        f"1차 익절가: {tp1:,.2f} USDT\n"
        f"참고 목표가(주문 아님): {tp2:,.2f} USDT\n"
    )
    if event == "PENDING":
        title = f"[BTCUSDT] {mode_label}{direction} 예상 진입가 확정"
        body = (
            "BTCUSDT 포지션 지정가가 정해져 체결 대기를 시작했습니다.\n\n"
            f"{price_lines}"
        )
    elif event == "ENTRY":
        title = f"[BTCUSDT] {mode_label}{direction} 포지션 진입 체결"
        body = f"BTCUSDT 포지션 지정가가 체결되었습니다.\n\n{price_lines}"
    elif event in ("TP1", "TP2", "SL"):
        if not exit_price:
            return False, "청산 가격이 완성되지 않음"
        event_label = "1차 익절" if event == "TP1" else "2차 익절" if event == "TP2" else "손절"
        pnl_line = ""
        if pnl_pct is not None:
            pnl = float(pnl_pct)
            pnl_line = f"수익률: {'+' if pnl >= 0 else ''}{pnl:.2f}%\n"
        title = f"[BTCUSDT] {mode_label}{direction} {event_label}"
        body = (
            f"BTCUSDT 포지션이 {event_label} 처리되었습니다.\n\n"
            f"방향: {direction}\n"
            f"진입가: {entry:,.2f} USDT\n"
            f"청산가: {exit_price:,.2f} USDT\n"
            f"{pnl_line}"
        )
    else:
        return False, f"지원하지 않는 거래 메일 이벤트: {event}"

    _send_message(sender, app_password, recipient, title, body)
    return True, recipient
