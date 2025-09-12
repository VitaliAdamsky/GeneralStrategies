import pandas as pd

def compute(df: pd.DataFrame, window: int = 14, column: str = "close") -> pd.DataFrame:
    """
    Вычисляет Exponential Moving Average (EMA)
    """
    ema = df[column].ewm(span=window, adjust=False).mean()
    df[f"ema_{window}"] = ema
    return df
