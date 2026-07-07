"""API 자격증명 저장/로드 (data/credentials.json)"""
import json
from dataclasses import dataclass
from backend.config import DATA_DIR

_CREDS_FILE = DATA_DIR / "credentials.json"


@dataclass
class Credentials:
    api_key:    str = ""
    secret_key: str = ""
    passphrase: str = ""

    def is_set(self) -> bool:
        return bool(self.api_key and self.secret_key and self.passphrase)


def load() -> Credentials:
    if _CREDS_FILE.exists():
        try:
            with open(_CREDS_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            return Credentials(
                api_key    = d.get("api_key", ""),
                secret_key = d.get("secret_key", ""),
                passphrase = d.get("passphrase", ""),
            )
        except Exception:
            pass
    return Credentials()


def save(api_key: str, secret_key: str, passphrase: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_CREDS_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"api_key": api_key, "secret_key": secret_key, "passphrase": passphrase},
            f, indent=2,
        )
