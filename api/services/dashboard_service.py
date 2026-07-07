from pathlib import Path

from fastapi.responses import FileResponse

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def frontend_exists() -> bool:
    return FRONTEND_DIST.exists()


async def serve_spa(_: str = ""):
    return FileResponse(str(FRONTEND_DIST / "index.html"))
