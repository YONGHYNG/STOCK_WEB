# 역할: HTTP API 경로를 백엔드 서비스에 연결하는 라우터.
from fastapi import APIRouter

from api.schemas.trading_schema import AutoTradePayload, CredentialsPayload, ModePayload, RiskSettingsPayload
from api.services import trading_control_service as svc

router = APIRouter()


@router.get("/api/risk-settings")
async def get_risk_settings():
    return await svc.get_risk_settings()


@router.post("/api/risk-settings")
async def save_risk_settings(payload: RiskSettingsPayload):
    return await svc.save_risk_settings(payload)


@router.post("/api/mode")
async def set_mode(payload: ModePayload):
    return await svc.set_mode(payload)


@router.post("/api/auto-trade")
async def set_auto_trade(payload: AutoTradePayload):
    return await svc.set_auto_trade(payload)


@router.post("/api/emergency-stop")
async def emergency_stop():
    return await svc.emergency_stop()


@router.post("/api/emergency-close")
async def emergency_close():
    return await svc.emergency_close()


@router.get("/api/credentials")
async def get_credentials():
    return await svc.get_credentials()


@router.post("/api/credentials")
async def save_credentials(payload: CredentialsPayload):
    return await svc.save_credentials(payload)
