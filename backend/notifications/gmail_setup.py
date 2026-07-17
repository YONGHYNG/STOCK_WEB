"""Gmail 주소와 앱 비밀번호를 로컬에 저장하고 테스트 메일을 보냅니다."""

from getpass import getpass

from backend.notifications.gmail_notifier import DEFAULT_RECIPIENT, save_gmail_config, send_test_email


def main() -> None:
    print("Google 계정에서 2단계 인증을 켜고 16자리 앱 비밀번호를 먼저 발급하세요.\n")
    sender = input("발신 Gmail 주소: ").strip()
    app_password = getpass("Google 앱 비밀번호(화면에 표시되지 않음): ").replace(" ", "").strip()
    if not sender or "@" not in sender:
        raise SystemExit("올바른 Gmail 주소를 입력하세요.")
    if not app_password:
        raise SystemExit("앱 비밀번호가 비어 있습니다.")

    print(f"테스트 메일 발송 중 → {DEFAULT_RECIPIENT}")
    send_test_email(sender, app_password, DEFAULT_RECIPIENT)
    save_gmail_config(sender, app_password, DEFAULT_RECIPIENT)
    print("Gmail 알림 연결 완료. 설정은 data/gmail_config.json에 저장되었습니다.")


if __name__ == "__main__":
    main()
