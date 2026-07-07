# 역할: HTTP API 경로를 백엔드 서비스에 연결하는 라우터.
from fastapi import APIRouter

from api.services import trading_control_service as svc

router = APIRouter()


@router.get("/api/status")
async def get_status():
    return await svc.get_status()
