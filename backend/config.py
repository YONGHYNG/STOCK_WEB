# 역할: 거래 심볼, 시간봉, 기본 설정값을 정의하는 파일.
from pathlib import Path

# backend/config.py의 상위 프로젝트 디렉터리를 기준으로 모든 실행 환경에서
# 데이터와 모델을 프로젝트 내부에 보관합니다.
BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
MODEL_DIR = BASE_DIR / "models"
DB_PATH = DATA_DIR / "trading.db"

SYMBOL = "BTCUSDT"
PRODUCT_TYPE = "USDT-FUTURES"

# 분석 대상 시간봉: 5m가 진입 기준이며 1H ATR은 손절·익절 거리에 사용합니다.
TIMEFRAMES = ["1m", "5m", "15m", "30m", "1H", "4H", "6H", "1D"]
DEFAULT_TIMEFRAME = "5m"
TIMEFRAME = DEFAULT_TIMEFRAME

# MA200/RSI/ATR/거래량 지표 안정화를 위해 최근 660개 확정 캔들을 유지합니다.
CANDLE_ANALYSIS_LIMIT = 660
RECENT_CANDLE_LIMIT_BY_TIMEFRAME = {tf: CANDLE_ANALYSIS_LIMIT for tf in TIMEFRAMES}
RECENT_CANDLE_LIMIT = RECENT_CANDLE_LIMIT_BY_TIMEFRAME[DEFAULT_TIMEFRAME]

BITGET_REST_BASE = "https://api.bitget.com"
BITGET_WS_PUBLIC = "wss://ws.bitget.com/v2/ws/public"
USE_DEMO_DATA = False
API_TIMEOUT_SECONDS = 8
REFRESH_INTERVAL_MS = 15000
INITIAL_CANDLE_LIMIT = CANDLE_ANALYSIS_LIMIT
REFRESH_CANDLE_LIMIT = 2

# Futures execution model
SPREAD_NORMAL_RATE = 0.0003
SPREAD_CAUTION_RATE = 0.0007
TAKER_FEE_RATE = 0.0006
MAKER_FEE_RATE = 0.0003
FUNDING_NORMAL_RATE = 0.0001
FUNDING_CAUTION_RATE = 0.0003
FUNDING_BLOCK_RATE = 0.0005

# 실거래 자동 진입은 가용 USDT 전체를 교차 마진 20배로 사용합니다.
AUTO_LIVE_LEVERAGE = 20
LIVE_LIMIT_ORDER_TIMEOUT_SECONDS = 60
