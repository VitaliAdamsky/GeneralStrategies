import matplotlib.pyplot as plt
import pandas as pd
import json

def save_equity_plot_png(result_path, equity_df):
    if equity_df.empty:
        return

    plt.figure(figsize=(10, 4))
    plt.plot(equity_df.index, equity_df["equity"], color="blue", linewidth=2)
    plt.title("Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Portfolio Value")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(result_path / "equity.png")
    plt.close()

def generate_result_path(symbol, timeframe, strategy_params):
    from pathlib import Path
    from datetime import datetime
    import hashlib

    base_path = Path("results") / symbol / timeframe
    base_path.mkdir(parents=True, exist_ok=True)

    strategy_id = strategy_params.get("strategy_id", "")
    run_id = strategy_params.get("run_id", datetime.now().strftime("%Y%m%d_%H%M%S"))
    folder_name = f"{run_id}_{strategy_id}"
    result_path = base_path / folder_name
    result_path.mkdir(parents=True, exist_ok=True)

    return result_path

def save_params(result_path, params):
    with open(result_path / "params.json", "w") as f:
        json.dump(params, f, indent=2)

def save_metrics(result_path, metrics):
    df = pd.DataFrame([metrics])
    df.to_csv(result_path / "metrics.csv", index=False)

def save_trades(result_path, trades_df):
    trades_df.to_csv(result_path / "trades.csv", index=False)

def save_trades_full(result_path, trades_df):
    trades_df.to_csv(result_path / "trades_full.csv", index=False)

def save_equity_curve(result_path, equity_df):
    equity_df.to_csv(result_path / "equity_curve.csv")

def save_exit_log(result_path, exit_log):
    if not exit_log:
        return
    df = pd.DataFrame(exit_log)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.sort_values("timestamp", inplace=True)
    df.to_csv(result_path / "exit_log.csv", index=False)

def save_entry_log(result_path, entry_log):
    if not entry_log:
        return
    df = pd.DataFrame(entry_log)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df.sort_values("timestamp", inplace=True)
    df.to_csv(result_path / "entry_log.csv", index=False)
