# 역할: Bitget 선물 API 연동을 담당하는 파일.
"""
Bitget USDT-Futures 인증 클라이언트
- API Key / Secret / Passphrase 기반 HMAC-SHA256 서명
- 잔고 조회, 포지션 조회, 시장가 주문, 포지션 청산
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Optional

import requests

from backend.config import API_TIMEOUT_SECONDS, BITGET_REST_BASE, PRODUCT_TYPE, SYMBOL


class BitgetPrivateClient:
    def __init__(self, api_key: str, secret_key: str, passphrase: str):
        self.api_key    = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase

    # ── 서명 / 헤더 ────────────────────────────────────────────────────────────

    def _sign(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        message = timestamp + method.upper() + path + body
        mac = hmac.new(self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        ts = str(int(time.time() * 1000))
        return {
            "ACCESS-KEY":        self.api_key,
            "ACCESS-SIGN":       self._sign(ts, method, path, body),
            "ACCESS-TIMESTAMP":  ts,
            "ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type":      "application/json",
            "locale":            "en-US",
        }

    # ── HTTP 래퍼 ──────────────────────────────────────────────────────────────

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        query = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
        full  = path + query
        res   = requests.get(
            BITGET_REST_BASE + full,
            headers=self._headers("GET", full),
            timeout=API_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        return self._unwrap(res.json())

    def _post(self, path: str, body: dict) -> dict:
        body_str = json.dumps(body, separators=(",", ":"))
        res = requests.post(
            BITGET_REST_BASE + path,
            headers=self._headers("POST", path, body_str),
            data=body_str,
            timeout=API_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
        return self._unwrap(res.json())

    @staticmethod
    def _unwrap(payload: dict) -> dict:
        if payload.get("code") not in (None, "00000"):
            raise RuntimeError(f"[{payload.get('code')}] {payload.get('msg', '알 수 없는 오류')}")
        return payload

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_account(self) -> dict:
        """USDT-Futures 계정 정보 (잔고, 증거금 등)"""
        data = self._get("/api/v2/mix/account/account", {
            "symbol":      SYMBOL,
            "productType": PRODUCT_TYPE,
            "marginCoin":  "USDT",
        })
        return data.get("data") or {}

    def get_positions(self) -> list[dict]:
        """현재 오픈 포지션 목록"""
        data = self._get("/api/v2/mix/position/allPosition", {
            "productType": PRODUCT_TYPE,
            "marginCoin":  "USDT",
        })
        raw = data.get("data") or []
        # 실제 보유 수량이 0보다 큰 포지션만
        return [p for p in raw if float(p.get("total", 0) or 0) > 0]

    def place_market_order(
        self,
        side: str,        # "buy" = LONG 진입/SHORT 청산,  "sell" = SHORT 진입/LONG 청산
        size: str,        # BTC 수량 (e.g. "0.001")
        trade_side: str,  # "open" = 신규,  "close" = 청산
    ) -> dict:
        """시장가 주문"""
        body = {
            "symbol":      SYMBOL,
            "productType": PRODUCT_TYPE,
            "marginMode":  "crossed",
            "marginCoin":  "USDT",
            "size":        size,
            "side":        side,
            "tradeSide":   trade_side,
            "orderType":   "market",
        }
        return (self._post("/api/v2/mix/order/placeOrder", body)).get("data") or {}

    def close_position(self, hold_side: str) -> dict:
        """
        포지션 전체 시장가 청산
        hold_side: "long" 또는 "short"
        """
        body = {
            "symbol":      SYMBOL,
            "productType": PRODUCT_TYPE,
            "holdSide":    hold_side,
        }
        return (self._post("/api/v2/mix/order/closePositions", body)).get("data") or {}
