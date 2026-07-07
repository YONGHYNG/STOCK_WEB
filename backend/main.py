import uvicorn

from backend.app.database import init_db


def main() -> None:
    init_db()
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
