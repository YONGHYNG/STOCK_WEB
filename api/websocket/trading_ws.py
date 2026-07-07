from fastapi import APIRouter, WebSocket

from api.services import trading_control_service as svc

router = APIRouter()


@router.websocket("/ws")
async def trading_websocket(ws: WebSocket):
    await svc.websocket_endpoint(ws)
