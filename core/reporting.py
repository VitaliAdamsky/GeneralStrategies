import os
import json
import csv
import hashlib
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import pandas as pd
from rich import print

RESULTS_DIR = Path("results")
RESULTS_DIR.mkdir(exist_ok=True)

def hash_params(params: dict) -> str:
    raw = json.dumps(params, sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:4]

def generate_result_path(symbol: str, timeframe: str, params: dict) -> Path:
    timestamp = datetime.now().strftime("%Y_%m_%d-%H_%M_%S")
    suffix = hash_params(params)
    folder_name = f"{symbol}_{timeframe}_{timestamp}_{suffix}"
    path = RESULTS_DIR / folder_name
    path.mkdir(parents=True, exist_ok=True)
    print(f"[bold green]📁 Создана папка отчёта: {path}[/bold green]")
    return path

def save_params(path: Path, params: dict):
    with open(path / f"{path.name}_params.json", "w", encoding="utf-8") as f:
        json.dump(params, f, indent=2)
    print(f"[green]✅ Параметры сохранены[/green]")

def save_metrics(path: Path, metrics: dict):
    with open(path / f"{path.name}_metrics.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Value"])
        for k, v in metrics.items():
            writer.writerow([k, v])
    print(f"[green]✅ Метрики сохранены[/green]")

def save_trades(path: Path, trades_df: pd.DataFrame):
    trades_df.to_csv(path / f"{path.name}_trades.csv", index=False)
    print(f"[green]✅ Агрегированные сделки сохранены[/green]")

def save_trades_full(path: Path, trades_full_df: pd.DataFrame):
    trades_full_df.to_csv(path / f"{path.name}_trades_full.csv", index=False)
    print(f"[green]✅ Все сделки сохранены[/green]")

def save_equity_curve(path: Path, equity_df: pd.DataFrame):
    plt.figure(figsize=(10, 4))
    plt.plot(equity_df.index, equity_df["equity"], label="Equity Curve", color="blue")
    plt.title("Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(path / f"{path.name}_equity_curve.png", dpi=150)
    plt.close()
    print(f"[green]✅ График доходности сохранён[/green]")

def save_quantstats_report(path: Path, html: str):
    with open(path / f"{path.name}_quantstats.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[green]✅ QuantStats отчёт сохранён[/green]")

def save_exit_log(path: Path, exit_events: list):
    """
    exit_events: список словарей:
    [
        {
            "timestamp": "2025-09-12 16:08:00",
            "price": 27350.0,
            "percent": 0.5,
            "exit_type": "atr",
            "reason": "Price >= entry + 1.0 ATR"
        },
        ...
    ]
    """
    df = pd.DataFrame(exit_events)
    df.to_csv(path / f"{path.name}_exit_log.csv", index=False)
    print(f"[green]✅ Лог выходов сохранён: {path.name}_exit_log.csv[/green]")
