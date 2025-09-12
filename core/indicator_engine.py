import pandas as pd
import ta  # pip install ta
from rich import print

def apply_indicators(df, indicators):
    """
    df: исходный DataFrame с колонками open, high, low, close, volume
    indicators: список словарей:
        [
            {"name": "rsi", "params": {"window": 14}, "group": "momentum"},
            {"name": "atr", "params": {"window": 14}, "group": "volatility"},
            {"name": "custom_func", "params": {...}, "group": "custom", "func": callable}
        ]
    Возвращает df с добавленными колонками
    """
    for ind in indicators:
        name = ind["name"]
        params = ind.get("params", {})
        group = ind.get("group", "misc")

        try:
            if "func" in ind:
                # Кастомная функция
                df = ind["func"](df, **params)
                print(f"[green]✅ Custom indicator applied: {name}[/green]")
            else:
                # TA-Lib через pandas-ta
                if name.lower() == "rsi":
                    df[f"{group}_{name}_{params['window']}"] = ta.momentum.RSIIndicator(close=df["close"], **params).rsi()
                elif name.lower() == "atr":
                    df[f"{group}_{name}_{params['window']}"] = ta.volatility.AverageTrueRange(high=df["high"], low=df["low"], close=df["close"], **params).average_true_range()
                elif name.lower() == "ema":
                    df[f"{group}_{name}_{params['window']}"] = ta.trend.EMAIndicator(close=df["close"], **params).ema_indicator()
                elif name.lower() == "macd":
                    macd = ta.trend.MACD(close=df["close"], **params)
                    df[f"{group}_{name}_line"] = macd.macd()
                    df[f"{group}_{name}_signal"] = macd.macd_signal()
                    df[f"{group}_{name}_diff"] = macd.macd_diff()
                else:
                    print(f"[yellow]⚠️ Unknown indicator: {name} — skipped[/yellow]")
        except Exception as e:
            print(f"[red]❌ Error applying {name}: {e}[/red]")

    return df
