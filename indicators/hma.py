import pandas as pd
import numpy as np

def compute(df: pd.DataFrame, window: int = 14, column: str = "close") -> pd.DataFrame:
    """
    Вычисляет Hull Moving Average (HMA)
    Формула: HMA(n) = WMA(2*WMA(n/2) - WMA(n)), sqrt(n)
    """
    def wma(series, period):
        weights = np.arange(1, period + 1)
        return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

    half = int(window / 2)
    sqrt_n = int(np.sqrt(window))

    wma_half = wma(df[column], half)
    wma_full = wma(df[column], window)
    raw_hma = 2 * wma_half - wma_full
    hma = wma(raw_hma, sqrt_n)

    df[f"hma_{window}"] = hma
    return df
