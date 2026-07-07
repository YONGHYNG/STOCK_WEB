# AI Trading Workspace - 멀티 타임프레임 / Windows / PyCharm용

BTCUSDT 선물 매매 판단 프로그램 기본 구조입니다.

---

## 실행 방법

```bash
# 의존성 설치 (최초 1회)
pip install -r requirements.txt

# GUI 실행
python main.py
```

---

## 추가된 기능 (v2)

### 매매 모드 (헤더 콤보박스)

| 모드 | 설명 |
|------|------|
| SIGNAL_ONLY | 신호만 분석, 주문 없음 (기본값) |
| PAPER_TRADING | 실제 주문 없이 모의매매 DB 기록 |
| LIVE_TRADING | Bitget 실제 주문 실행 |

> **기본값은 SIGNAL_ONLY** — 모드 변경 시 확인 팝업이 뜹니다.

### 리스크 설정 탭

`data/risk_settings.json` 에 저장됩니다.

- 1회 주문 수량 (BTC)
- 1회 최대 손실률 / 일일 최대 손실률
- 연속 손실 정지 횟수
- 자동매매 신뢰도 기준 (%)
- 재진입 대기 시간 (초)
- 최대 레버리지
- **실거래 허용 여부** (명시적으로 체크해야 LIVE 자동매매 가능)

### 모의매매 (PAPER_TRADING)

- 실제 Bitget 주문 없이 `trades` 테이블에 `trade_type='PAPER'` 로 기록
- 2초마다 현재가로 TP/SL 자동 감시
- 투자 복기 탭에서 **구분** 컬럼으로 LIVE / PAPER 구분

### 백테스트 탭

- DB에 저장된 캔들 기반 단순 시뮬레이션
- 시작일/종료일/시간봉/초기자본/수수료/슬리피지 설정
- 결과: 총 거래 / 승률 / 누적수익 / MDD / 손익비 / 최종 자본

### 긴급정지 버튼 (헤더 우측)

- 자동매매 즉시 OFF
- 추가 주문 차단
- 포지션이 있으면 **청산 여부를 사용자에게 확인 후** 처리

### 자동매매 안전장치

진입 전 아래 조건을 모두 검사합니다:
1. 자동매매 활성화 여부
2. 모드 확인 (SIGNAL_ONLY 이면 차단)
3. 방향이 LONG/SHORT 인지
4. confidence ≥ 임계값
5. 재진입 대기 시간 경과 여부
6. 일일 손실 한도 초과 여부
7. 연속 손실 한도 초과 여부
8. 거래소 포지션 중복 진입 방지
9. LIVE 모드 시 API 키 + 실거래 허용 체크 확인
10. 긴급정지 여부

---

## 실거래 전 주의사항

> **경고: 실제 자금 손실 위험이 있습니다.**

1. 반드시 `PAPER_TRADING` 모드에서 충분히 테스트 후 실거래 전환
2. `리스크 설정 탭` → **실거래 허용 체크박스**를 명시적으로 활성화해야 LIVE 자동매매 가능
3. `data/credentials.json` 에 API 키가 저장됩니다 — 읽기 전용(Read Only) 키로 먼저 테스트
4. 실거래 자동매매 활성화 시 **반드시 확인 팝업이 뜹니다**
5. 1회 주문 수량은 리스크 설정에서 제어 (기본 0.001 BTC)
6. 시장 상황에 따라 AI 신호가 틀릴 수 있습니다. 100% 신뢰 금지

---

## 파일 구조

```
backend/
  gui.py              - 데스크톱 GUI
  ai_engine.py        - 멀티타임프레임 분석 엔진
  bitget_client.py    - Bitget 공개 API
  bitget_private_client.py - Bitget 인증 API
  backtester.py       - 백테스트 엔진
  paper_trader.py     - 모의매매
  risk_manager.py     - 리스크 안전조건 검사
  risk_settings.py    - 리스크 설정 저장/로드
  trading_modes.py    - 매매 모드 열거형
  database.py         - SQLite CRUD
  credentials.py      - API 자격증명 저장/로드
  config.py           - 설정 상수
api/
  server.py           - FastAPI 라우터/웹소켓/백그라운드 루프
  main.py             - 웹 API 서버 실행 진입점
frontend/
  src/                - React 웹 대시보드
data/
  trading.db          - SQLite DB (캔들, 신호, 거래 기록)
  credentials.json    - API 키 (로컬 저장)
  risk_settings.json  - 리스크 설정
```

--- 실제 주문은 넣지 않으며, Bitget 실시간 캔들 조회·SQLite 저장·규칙 기반 신호 점수·손절가/익절가·역사적 신고가/신저가 처리를 확인하는 용도입니다.

## 포함 기능

### 1. 멀티 타임프레임 분석

기본 시간봉은 5분봉이지만, 판단에는 아래 시간봉을 함께 사용합니다.

```text
5분 / 15분 / 30분 / 1시간 / 6시간 / 일봉 / 주봉 / 월봉
```

역할은 다음과 같습니다.

```text
5분봉   → 단기 진입 타이밍
15분봉  → 단기 추세 확인
30분봉  → 중기 방향 확인
1시간봉 → 큰 흐름 확인
6시간봉 → 주요 추세 확인
일봉    → 장기 추세 확인
주봉    → 큰 사이클 확인
월봉    → 6년 전체 흐름 확인
```

### 2. SQLite DB 구조

DB는 여러 개로 나누지 않고 하나의 SQLite 파일을 사용합니다.

```text
data/trading.db
```

테이블도 시간봉별로 따로 만들지 않고 `candles` 단일 테이블에 `timeframe` 컬럼으로 구분합니다.

```sql
CREATE TABLE candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);
```

예시:

```text
BTCUSDT / 5m  / 2026-06-29 10:00 / ...
BTCUSDT / 15m / 2026-06-29 10:00 / ...
BTCUSDT / 1H  / 2026-06-29 10:00 / ...
BTCUSDT / 1D  / 2026-06-29 00:00 / ...
```

### 3. 6년치 데이터와 실시간 분석 구조

6년치 전체 데이터를 버튼 누를 때마다 분석하지 않습니다.

```text
6년치 데이터 → 학습 / 백테스트 / 신고가·신저가 기준값 생성
실시간 판단 → 각 시간봉의 최근 캔들만 조회
```

기본 조회 개수:

```text
5m: 300개
15m: 300개
30m: 300개
1H: 300개
6H: 200개
1D: 200개
1W: 100개
1M: 72개
```

### 4. 기술적 지표

현재 버전에서 계산하는 지표:

```text
RSI 14
EMA 20
EMA 60
MACD
MACD Signal
MACD Histogram
ATR 14
Volume MA20
```

### 5. LONG / SHORT 점수

현재는 딥러닝이 아니라 규칙 기반 분석입니다. 화면의 LONG/SHORT 값은 백테스트로 검증된 확률이 아니라 조건별 가중치를 합산한 신호 점수입니다.

```text
EMA20 > EMA60        → LONG 가점
MACD Histogram 상승 → LONG 가점
RSI 과매도          → LONG 가점
RSI 과열            → LONG 감점
거래량 급증         → 추세 방향에 따라 가점/감점
상위 시간봉 LONG    → LONG 점수 보정
상위 시간봉 SHORT   → SHORT 점수 보정
```

나중에 `backend/ai_engine.py`의 `TradingAIEngine` 내부를 PyTorch, LightGBM, XGBoost 모델로 교체하면 됩니다.

### 6. 손절가 / 익절가

ATR 기반으로 계산합니다.

LONG:

```text
손절가 = 진입가 - ATR × 1.5
1차 익절가 = 진입가 + 손절폭 × 2
2차 익절가 = 진입가 + 손절폭 × 3
```

SHORT:

```text
손절가 = 진입가 + ATR × 1.5
1차 익절가 = 진입가 - 손절폭 × 2
2차 익절가 = 진입가 - 손절폭 × 3
```

### 7. 역사적 신고가 처리

현재가가 DB의 최고가 이상이면 `all_time_high_mode=True`가 됩니다.

처리 기준:

```text
기존 저항선 기반 목표가 사용 X
ATR 기준 목표가 사용
RSI 80 이상이면 추격매수 위험 반영
거래량이 20봉 평균의 2배 이상이면 변동성 위험 반영
```

GUI 표시:

```text
신고가 모드: ON
```

### 8. 역사적 신저가 처리

현재가가 DB의 최저가 이하이면 `all_time_low_mode=True`가 됩니다.

처리 기준:

```text
기존 지지선 기반 목표가/손절가 신뢰 X
지지선이 무너진 상태로 판단
ATR 기준 목표가/손절가 사용
RSI 20 이하이면 과매도 반등 가능성 표시
EMA 역배열이면 LONG 역추세 진입 위험 증가
거래량이 20봉 평균의 2배 이상이면 투매/변동성 위험 반영
MACD 하락 지속이면 추가 하락 위험 반영
```

GUI 표시:

```text
신저가 모드: ON
```

### 9. PySide6 GUI

화면 표시 항목:

```text
현재가
추천 방향
LONG 점수
SHORT 점수
신뢰도
진입가
손절가
1차 익절가
2차 익절가
손익비
신고가 모드
신저가 모드
시간봉별 방향성
AI 분석 근거 로그
```

## Windows 실행 방법

압축을 풀고 PyCharm에서 폴더를 엽니다.

패키지 설치:

```cmd
scripts\install_windows.bat
```

실행:

```cmd
scripts\run_windows.bat
```

직접 실행:

```cmd
python -m api.main
```

6년치 CSV 다운로드:

```cmd
python -m backend.market.download_bitget_6y 5m 6
python -m backend.market.download_bitget_6y 1H 6
```

CSV 임포트:

```cmd
python -m backend.market.import_csv_to_sqlite data/bitget_BTCUSDT_5m_6y.csv 5m
```

`backend/config.py`의 `USE_DEMO_DATA`가 `False`이면 Bitget API 실패 시 데모 데이터로 조용히 대체하지 않고 GUI에 오류 상태를 표시합니다.

## 주요 파일

```text
backend/config.py       멀티 시간봉, DB 경로, 리스크 설정
backend/database.py     SQLite 테이블 생성/조회/저장
backend/indicator.py    RSI, EMA, MACD, ATR 계산
backend/ai_engine.py    LONG/SHORT 점수, 손절/익절, 신고가/신저가 처리
backend/gui.py          PySide6 블랙 대시보드 화면
backend/bitget_client.py Bitget API/데모 모드 분리 구조
docs/CODEX_PROMPT.md Codex에게 시킬 작업 프롬프트
```

## 주의사항

이 프로젝트는 투자 조언이나 실제 수익을 보장하지 않습니다. 실제 주문 기능은 포함되어 있지 않습니다. 자동매매를 붙이기 전에는 반드시 백테스트와 모의투자를 먼저 진행해야 합니다.
