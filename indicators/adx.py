import pandas as pd

def compute(df: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """
    Вычисляет ADX, DI+, DI- вручную.
    Добавляет колонки:
        - di_plus_{window}
        - di_minus_{window}
        - adx_{window}
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]

    # === Directional Movement
    up_move = high.diff()
    down_move = low.diff().abs()

    plus_dm = ((up_move > down_move) & (up_move > 0)) * up_move
    minus_dm = ((down_move > up_move) & (low.shift() > low)) * down_move

    # === True Range
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # === Smoothed Averages
    atr = tr.rolling(window).mean()
    plus_di = 100 * (plus_dm.rolling(window).mean() / atr)
    minus_di = 100 * (minus_dm.rolling(window).mean() / atr)

    # === DX and ADX
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di)) * 100
    adx = dx.rolling(window).mean()

    df[f"di_plus_{window}"] = plus_di
    df[f"di_minus_{window}"] = minus_di
    df[f"adx_{window}"] = adx

    return df
