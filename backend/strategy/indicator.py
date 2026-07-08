# 역할: 거래량/추세/RSI 전략에 필요한 지표를 pandas로 계산합니다.
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


def add_indicators(candles: list[dict] | pd.DataFrame) -> pd.DataFrame:
    df = candles.copy() if isinstance(candles, pd.DataFrame) else to_dataframe(candles)
    if df.empty:
        return df
    out = df.copy()
    out["ma90"] = out["close"].rolling(90).mean()
    out["ma200"] = out["close"].rolling(200).mean()
    out["rsi14"] = _rsi(out["close"], 14)
    out["atr14"] = _atr(out, 14)
    out["volume_ma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio"] = out["volume"] / out["volume_ma20"].replace(0, 1e-9)
    candle_range = (out["high"] - out["low"]).replace(0, 1e-9)
    out["upper_wick"] = out["high"] - out[["open", "close"]].max(axis=1)
    out["lower_wick"] = out[["open", "close"]].min(axis=1) - out["low"]
    out["body_ratio"] = (out["close"] - out["open"]).abs() / candle_range
    return out


__all__ = ["add_indicators", "to_dataframe"]
