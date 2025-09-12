import pandas as pd

def compute(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    Вычисляет Average True Range (ATR) вручную.
    Добавляет колонку: atr_{window}
    """
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()

    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window).mean()

    df[f"atr_{window}"] = atr
    return df
