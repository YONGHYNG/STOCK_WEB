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
        try:
            payload = res.json()
        except ValueError:
            res.raise_for_status()
            raise RuntimeError("Bitget에서 해석할 수 없는 응답을 받았습니다")
        # Bitget은 인증 오류도 HTTP 400으로 반환하므로 HTTP 예외보다
        # 응답 본문의 code/msg를 먼저 표시해야 원인을 알 수 있다.
        return self._unwrap(payload)

    def _post(self, path: str, body: dict) -> dict:
        body_str = json.dumps(body, separators=(",", ":"))
        res = requests.post(
            BITGET_REST_BASE + path,
            headers=self._headers("POST", path, body_str),
            data=body_str,
            timeout=API_TIMEOUT_SECONDS,
        )
        try:
            payload = res.json()
        except ValueError:
            res.raise_for_status()
            raise RuntimeError("Bitget에서 해석할 수 없는 응답을 받았습니다")
        return self._unwrap(payload)

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
        data = self._get("/api/v2/mix/position/all-position", {
            "productType": PRODUCT_TYPE,
            "marginCoin":  "USDT",
        })
        raw = data.get("data") or []
        # 실제 보유 수량이 0보다 큰 포지션만
        return [p for p in raw if float(p.get("total", 0) or 0) > 0]

    def get_pending_orders(self) -> list[dict]:
        """현재 BTCUSDT 일반 미체결 주문을 조회합니다."""
        data = self._get("/api/v2/mix/order/orders-pending", {
            "productType": PRODUCT_TYPE,
            "symbol": SYMBOL,
        })
        return (data.get("data") or {}).get("entrustedList") or []

    def get_position_history(self, limit: int = 20) -> list[dict]:
        """최근 BTCUSDT 청산 포지션 이력을 조회합니다."""
        data = self._get("/api/v2/mix/position/history-position", {
            "productType": PRODUCT_TYPE,
            "symbol": SYMBOL,
            "limit": str(limit),
        })
        return (data.get("data") or {}).get("list") or []

    def get_contract_config(self) -> dict:
        """BTCUSDT 계약의 최소 주문 수량과 수량 단위를 조회합니다."""
        data = self._get("/api/v2/mix/market/contracts", {
            "productType": PRODUCT_TYPE,
            "symbol": SYMBOL,
        })
        contracts = data.get("data") or []
        return contracts[0] if contracts else {}

    def set_leverage(self, leverage: int) -> dict:
        """BTCUSDT 교차 마진 레버리지를 설정합니다."""
        body = {
            "symbol": SYMBOL,
            "productType": PRODUCT_TYPE,
            "marginCoin": "USDT",
            "leverage": str(int(leverage)),
        }
        return (self._post("/api/v2/mix/account/set-leverage", body)).get("data") or {}

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
        return (self._post("/api/v2/mix/order/place-order", body)).get("data") or {}

    def place_limit_order(
        self,
        side: str,
        size: str,
        price: str,
        trade_side: str = "open",
        client_oid: Optional[str] = None,
    ) -> dict:
        """지정가 주문. 체결되지 않으면 거래소 미체결 주문으로 유지됩니다."""
        body = {
            "symbol": SYMBOL,
            "productType": PRODUCT_TYPE,
            "marginMode": "crossed",
            "marginCoin": "USDT",
            "size": size,
            "price": price,
            "side": side,
            "tradeSide": trade_side,
            "orderType": "limit",
            "force": "gtc",
        }
        if client_oid:
            body["clientOid"] = client_oid
        return (self._post("/api/v2/mix/order/place-order", body)).get("data") or {}

    def cancel_order(self, order_id: str) -> dict:
        """미체결 지정가 주문 취소."""
        body = {
            "symbol": SYMBOL,
            "productType": PRODUCT_TYPE,
            "marginCoin": "USDT",
            "orderId": order_id,
        }
        return (self._post("/api/v2/mix/order/cancel-order", body)).get("data") or {}

    def get_order_detail(self, order_id: str) -> dict:
        """지정가 주문의 체결·부분 체결·취소 상태를 조회합니다."""
        data = self._get("/api/v2/mix/order/detail", {
            "symbol": SYMBOL,
            "productType": PRODUCT_TYPE,
            "orderId": order_id,
        })
        return data.get("data") or {}

    def place_tpsl_limit_order(
        self,
        plan_type: str,
        hold_side: str,
        size: str,
        trigger_price: str,
        execute_price: str,
    ) -> dict:
        """포지션 익절/손절 트리거 도달 시 지정가로 청산하는 거래소 주문."""
        body = {
            "marginCoin": "USDT",
            "productType": PRODUCT_TYPE,
            "symbol": SYMBOL,
            "planType": plan_type,
            "triggerPrice": trigger_price,
            "triggerType": "mark_price",
            "executePrice": execute_price,
            "holdSide": hold_side.lower(),
            "size": size,
        }
        return (self._post("/api/v2/mix/order/place-tpsl-order", body)).get("data") or {}

    def place_position_tpsl(
        self,
        hold_side: str,
        take_profit_price: str,
        stop_loss_price: str,
    ) -> list[dict]:
        """현재 포지션 전체에 시장가 실행 방식의 TP와 SL을 동시에 설정합니다."""
        body = {
            "marginCoin": "USDT",
            "productType": PRODUCT_TYPE,
            "symbol": SYMBOL,
            "stopSurplusTriggerPrice": take_profit_price,
            "stopSurplusTriggerType": "mark_price",
            "stopSurplusExecutePrice": "0",
            "stopLossTriggerPrice": stop_loss_price,
            "stopLossTriggerType": "mark_price",
            "stopLossExecutePrice": "0",
            "holdSide": hold_side.lower(),
        }
        data = (self._post("/api/v2/mix/order/place-pos-tpsl", body)).get("data") or []
        return data if isinstance(data, list) else []

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
        return (self._post("/api/v2/mix/order/close-positions", body)).get("data") or {}
