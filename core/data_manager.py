import pandas as pd
from pathlib import Path
from rich.progress import track
from rich.console import Console
from core.enums import Timeframes  # ✅ импорт из правильного места, без циклических зависимостей

console = Console()

def load_market_data(symbols: list[str], timeframes: list[Timeframes], base_dir="kline_data", start_date=None, end_date=None):
    """
    Загружает свечи по символам и таймфреймам (Enum Timeframes).
    Фильтрует по start_date / end_date, если заданы.
    Возвращает: market_data[symbol][timeframe.value] = DataFrame
    """
    market_data = {}

    for symbol in symbols:
        market_data[symbol] = {}
        for tf_enum in track(timeframes, description=f"[cyan]Загрузка {symbol}...[/cyan]"):
            tf_str = tf_enum.value  # ✅ получаем строку из Enum
            csv_path = Path(base_dir) / tf_str / f"{symbol}.csv"  # ✅ безопасное построение пути

            if not csv_path.exists():
                console.print(f"[bold red]❌ Нет файла: {csv_path}[/bold red]")
                continue

            try:
                df = pd.read_csv(csv_path, parse_dates=["datetime"])
                df.set_index("datetime", inplace=True)
                df = df[["open", "high", "low", "close", "volume"]]

                if start_date:
                    df = df[df.index >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df.index <= pd.to_datetime(end_date)]

                market_data[symbol][tf_str] = df
                console.print(f"[green]✅ Загружено: {symbol} {tf_str} ({len(df)} строк)[/green]")
            except Exception as e:
                console.print(f"[bold red]⚠️ Ошибка при загрузке {symbol} {tf_str}: {e}[/bold red]")

    return market_data
