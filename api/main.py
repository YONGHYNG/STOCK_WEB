# 역할: FastAPI 서버 실행과 라우터 등록을 담당하는 진입점.
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers.dashboard_router import router as dashboard_router
from api.routers.position_router import router as position_router
from api.routers.strategy_router import router as strategy_router
from api.routers.trade_log_router import router as trade_log_router
from api.routers.trading_router import router as trading_router
from api.services import dashboard_service
from api.services.trading_control_service import startup_event
from api.websocket.trading_ws import router as websocket_router
from backend.database import init_db

app = FastAPI(title="Trading AI Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard_router)
app.include_router(strategy_router)
app.include_router(trade_log_router)
app.include_router(trading_router)
app.include_router(position_router)
app.include_router(websocket_router)

if dashboard_service.frontend_exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(dashboard_service.FRONTEND_DIST / "assets")),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return await dashboard_service.serve_spa(full_path)


@app.on_event("startup")
async def on_startup():
    init_db()
    await startup_event()


def main() -> None:
    init_db()
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)

if __name__ == "__main__":
    main()
