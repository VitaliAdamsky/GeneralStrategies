import pandas as pd
from pathlib import Path
from rich.progress import track

def load_market_data(symbols, timeframes, base_dir="kline_data", start_date=None, end_date=None):
    """
    Загружает свечи по символам и таймфреймам.
    Фильтрует по start_date / end_date, если заданы.
    Возвращает: market_data[symbol][timeframe] = DataFrame
    """
    market_data = {}

    for symbol in symbols:
        market_data[symbol] = {}
        for timeframe in track(timeframes, description=f"[cyan]Загрузка {symbol}...[/cyan]"):
            csv_path = Path(base_dir) / timeframe / f"{symbol}.csv"
            if not csv_path.exists():
                print(f"[bold red]❌ Нет файла: {csv_path}[/bold red]")
                continue

            try:
                df = pd.read_csv(csv_path, parse_dates=["datetime"])
                df.set_index("datetime", inplace=True)
                df = df[["open", "high", "low", "close", "volume"]]

                # === Фильтрация по дате
                if start_date:
                    df = df[df.index >= pd.to_datetime(start_date)]
                if end_date:
                    df = df[df.index <= pd.to_datetime(end_date)]

                market_data[symbol][timeframe] = df
                print(f"[green]✅ Загружено: {symbol} {timeframe} ({len(df)} строк)[/green]")
            except Exception as e:
                print(f"[bold red]⚠️ Ошибка при загрузке {symbol} {timeframe}: {e}[/bold red]")

    return market_data
