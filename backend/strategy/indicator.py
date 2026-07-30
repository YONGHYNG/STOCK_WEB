# 역할: 거래량/추세/RSI 전략에 필요한 지표를 pandas로 계산합니다.
from __future__ import annotations

import pandas as pd


def to_dataframe(candles: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(candles)
    if df.empty:
        return df
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = range(len(df))
    return df.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """고점·저점 방향성을 이용해 ADX를 계산합니다."""
    up_move = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = true_range.rolling(period).mean().replace(0, 1e-9)
    plus_di = 100 * plus_dm.rolling(period).mean() / atr
    minus_di = 100 * minus_dm.rolling(period).mean() / atr
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)
    return dx.rolling(period).mean()


def add_indicators(candles: list[dict] | pd.DataFrame) -> pd.DataFrame:
    df = candles.copy() if isinstance(candles, pd.DataFrame) else to_dataframe(candles)
    if df.empty:
        return df
    out = df.copy()
    out["ema20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["ema50"] = out["close"].ewm(span=50, adjust=False).mean()
    out["ma90"] = out["close"].rolling(90).mean()
    out["ma200"] = out["close"].rolling(200).mean()
    out["ema20_slope"] = out["ema20"].diff()
    out["ma90_slope"] = out["ma90"].diff()
    out["rsi14"] = _rsi(out["close"], 14)
    out["atr14"] = _atr(out, 14)
    out["adx14"] = _adx(out, 14)
    out["bb_mid"] = out["close"].rolling(20).mean()
    bb_std = out["close"].rolling(20).std(ddof=0)
    out["bb_upper"] = out["bb_mid"] + bb_std * 2
    out["bb_lower"] = out["bb_mid"] - bb_std * 2
    out["bb_width"] = (
        (out["bb_upper"] - out["bb_lower"])
        / out["bb_mid"].replace(0, 1e-9)
    )
    out["volume_ma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / out["volume_ma20"].replace(0, 1e-9)
    typical_price = (out["high"] + out["low"] + out["close"]) / 3
    volume_sum = out["volume"].rolling(90).sum()
    out["vwap"] = (typical_price * out["volume"]).rolling(90).sum() / volume_sum.replace(0, 1e-9)
    candle_range = (out["high"] - out["low"]).replace(0, 1e-9)
    out["upper_wick"] = out["high"] - out[["open", "close"]].max(axis=1)
    out["lower_wick"] = out[["open", "close"]].min(axis=1) - out["low"]
    out["body_ratio"] = (out["close"] - out["open"]).abs() / candle_range
    return out


__all__ = ["add_indicators", "to_dataframe"]
