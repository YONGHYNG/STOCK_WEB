# 역할: 실시간 신호와 로그를 전달하는 웹소켓 라우터.
from fastapi import APIRouter, WebSocket

from api.services import trading_control_service as svc

router = APIRouter()


@router.websocket("/ws")
async def trading_websocket(ws: WebSocket):
    await svc.websocket_endpoint(ws)
