import pandas as pd

def compute(df: pd.DataFrame, window: int = 14, column: str = "close") -> pd.DataFrame:
    delta = df[column].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    df[f"rsi_{window}"] = rsi
    return df
