from fastapi import APIRouter

from api.services import trading_control_service as svc

router = APIRouter()


@router.get("/api/trades")
async def get_trades():
    return await svc.get_trades()
