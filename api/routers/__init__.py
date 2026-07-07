# 역할: HTTP API 경로를 백엔드 서비스에 연결하는 라우터.
from api.routers.dashboard_router import router as dashboard_router
from api.routers.position_router import router as position_router
from api.routers.strategy_router import router as strategy_router
from api.routers.trade_log_router import router as trade_log_router
from api.routers.trading_router import router as trading_router

__all__ = [
    "dashboard_router",
    "position_router",
    "strategy_router",
    "trade_log_router",
    "trading_router",
]
