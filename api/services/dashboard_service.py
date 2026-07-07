# 역할: 대시보드 표시 데이터를 조합하는 서비스.
from pathlib import Path

from fastapi.responses import FileResponse

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def frontend_exists() -> bool:
    return FRONTEND_DIST.exists()


async def serve_spa(_: str = ""):
    return FileResponse(str(FRONTEND_DIST / "index.html"))
