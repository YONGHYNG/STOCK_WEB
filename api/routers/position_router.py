# 역할: HTTP API 경로를 백엔드 서비스에 연결하는 라우터.
from fastapi import APIRouter

from api.schemas.position_schema import OrderPayload, PaperPendingOrderPayload
from api.services import trading_control_service as svc

router = APIRouter()


@router.post("/api/order")
async def place_order(payload: OrderPayload):
    return await svc.place_order(payload)


@router.post("/api/paper-pending-order")
async def place_paper_pending_order(payload: PaperPendingOrderPayload):
    return await svc.place_paper_pending_order(payload)


@router.post("/api/close-position")
async def close_position():
    return await svc.close_position()
