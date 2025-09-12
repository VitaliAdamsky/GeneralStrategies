import pandas as pd

def compute(df: pd.DataFrame, window: int = 14, column: str = "close") -> pd.DataFrame:
    """
    Вычисляет Simple Moving Average (SMA)
    """
    sma = df[column].rolling(window).mean()
    df[f"sma_{window}"] = sma
    return df
