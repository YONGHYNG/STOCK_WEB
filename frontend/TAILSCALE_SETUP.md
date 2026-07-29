# 모바일 데이터 연결 설정

이 앱의 백엔드와 데이터는 PC에 그대로 두고 Tailscale 사설망을 통해 접속합니다.
공유기 포트포워딩이나 공인 인터넷 공개는 사용하지 않습니다.

1. PC에 Tailscale을 설치하고 로그인합니다.
2. Android 휴대폰에도 Google Play의 Tailscale 앱을 설치합니다.
3. PC와 동일한 계정으로 로그인하고 Tailscale 연결을 켭니다.
4. PC에서 아래 명령으로 Tailscale IPv4 주소를 확인합니다.

   ```powershell
   & 'C:\Program Files\Tailscale\tailscale.exe' ip -4
   ```

5. PC에서 Trading AI 백엔드를 실행합니다.
6. Android Trading AI 앱의 `서버 설정`에 위의 `100.x.x.x` 주소를 입력합니다.
   포트를 생략하면 앱이 자동으로 `8000`을 사용합니다.
7. `연결 확인`을 누르고 상태가 `연결됨`인지 확인합니다.

PC, 백엔드 서버, PC Tailscale이 켜져 있어야 휴대폰의 LTE/5G에서도 사용할 수 있습니다.
