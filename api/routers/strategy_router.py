from fastapi import APIRouter

from api.schemas.strategy_schema import BacktestPayload
from api.services import trading_control_service as svc

router = APIRouter()


@router.get("/api/signal")
async def get_signal():
    return await svc.get_signal()


@router.post("/api/backtest")
async def run_backtest(payload: BacktestPayload):
    return await svc.run_backtest(payload)
