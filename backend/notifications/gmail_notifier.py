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


def _position_share_percent(result: dict) -> float:
    explicit = result.get("position_size_percent")
    if explicit is not None:
        return max(0.0, min(100.0, float(explicit)))
    ratio = result.get("position_size_ratio")
    if ratio is not None:
        return max(0.0, min(100.0, float(ratio) * 100))
    return 100.0


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
    position_share = _position_share_percent(result)
    size_btc = float(result.get("position_size_btc") or result.get("size_btc") or 0)
    entry_stage = int(result.get("entry_stage") or (1 if position_share < 100 else 2))
    second_entry = float(result.get("second_entry_price") or 0)
    third_entry = float(result.get("third_entry_price") or 0)
    added_entry = float(result.get("added_entry_price") or third_entry or second_entry or 0)
    added_size = float(result.get("added_size_btc") or 0)
    average_entry = float(result.get("average_entry_price") or entry)
    if direction not in ("LONG", "SHORT") or not entry:
        return False, "포지션 방향 또는 진입 가격이 완성되지 않음"
    if event in ("PENDING", "ENTRY") and (not tp1 or not tp2 or (entry_stage >= 2 and not stop)):
        return False, "포지션 또는 진입·손절·익절 가격이 완성되지 않음"

    mode_label = f"{mode} " if mode else ""
    price_lines = (
        f"방향: {direction}\n"
        f"진입 비중: {position_share:g}%\n"
        + (f"진입 수량: {size_btc:.8f} BTC\n" if size_btc else "") +
        f"진입 지정가: {entry:,.2f} USDT\n"
        + (f"손절가: {stop:,.2f} USDT\n" if stop else "손절가: 미설정 (2차 진입 후 활성화)\n") +
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
        title = f"[BTCUSDT] {mode_label}{direction} 최초 진입 · {position_share:g}%"
        body = f"BTCUSDT 첫 포지션이 체결되었습니다.\n\n{price_lines}"
    elif event == "ADD":
        if not added_entry:
            return False, "추가 진입 가격이 완성되지 않음"
        title = f"[BTCUSDT] {mode_label}{direction} 추가 진입 · 총 {position_share:g}%"
        body = (
            f"BTCUSDT {entry_stage}차 추가 진입이 체결되었습니다.\n\n"
            f"추가 체결가: {added_entry:,.2f} USDT\n"
            + (f"추가 수량: {added_size:.8f} BTC\n" if added_size else "") +
            f"현재 평균단가: {average_entry:,.2f} USDT\n"
            f"현재 손절가: {stop:,.2f} USDT\n"
            f"현재 총 비중: {position_share:g}%\n"
        )
    elif event in ("TP1", "TP2", "SL", "TRAILING_EXIT", "SESSION_EXIT", "EXIT"):
        if not exit_price:
            return False, "청산 가격이 완성되지 않음"
        event_label = {
            "TP1": "1차 분할익절", "TP2": "2차 분할익절", "SL": "손절",
            "TRAILING_EXIT": "추적 청산", "SESSION_EXIT": "다음 세션 전 청산",
            "EXIT": "포지션 청산",
        }[event]
        pnl_line = ""
        if pnl_pct is not None:
            pnl = float(pnl_pct)
            pnl_line = f"수익률: {'+' if pnl >= 0 else ''}{pnl:.2f}%\n"
        realized = result.get("realized_pnl_amount")
        remaining = result.get("remaining_size_btc")
        title = f"[BTCUSDT] {mode_label}{direction} {event_label}"
        body = (
            f"BTCUSDT 포지션이 {event_label} 처리되었습니다.\n\n"
            f"방향: {direction}\n"
            f"진입 비중: {position_share:g}%\n"
            + (f"진입 수량: {size_btc:.8f} BTC\n" if size_btc else "") +
            f"진입가: {entry:,.2f} USDT\n"
            f"청산가: {exit_price:,.2f} USDT\n"
            f"{pnl_line}"
            + (f"이번 실현손익: {float(realized):+.8f} USDT\n" if realized is not None else "")
            + (f"잔여 수량: {float(remaining):.8f} BTC\n" if remaining is not None else "")
        )
    else:
        return False, f"지원하지 않는 거래 메일 이벤트: {event}"

    _send_message(sender, app_password, recipient, title, body)
    return True, recipient
