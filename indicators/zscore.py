import pandas as pd

def compute(df: pd.DataFrame, window: int = 20, column: str = "close") -> pd.DataFrame:
    """
    Вычисляет Z-Score: (price - mean) / std
    Добавляет колонку: zscore_{window}
    """
    mean = df[column].rolling(window).mean()
    std = df[column].rolling(window).std()
    z = (df[column] - mean) / std
    df[f"zscore_{window}"] = z
    return df
