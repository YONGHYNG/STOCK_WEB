import uvicorn

from backend.database import init_db


def main() -> None:
    init_db()
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
