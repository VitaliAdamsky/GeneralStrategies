import matplotlib
matplotlib.use("Agg")

import backtrader as bt
import pandas as pd
import hashlib
from datetime import datetime
from itertools import product
from rich.console import Console
from rich.progress import track
import quantstats as qs

from core import (
    load_market_data,
    generate_param_grid,
    generate_result_path,
    save_params,
    save_metrics,
    save_trades,
    save_trades_full,
    save_equity_curve,
    save_equity_plot_png,
    save_exit_log,
    save_entry_log,
    plot_strategy_chart,
    apply_indicators
)
from core.take_profit_config import TakeProfitMode
from strategies.rsi_atr_strategy import SuperStrategy

console = Console()

SLIPPAGE = 0.0005
COMMISSION_MODEL = 0.00055

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAMES = ["1D", "12H"]
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"
INITIAL_CASH = 100000

param_ranges = {
    "rsi_period": [14, 21],
    "atr_period": [14],
    "take_profit": [{
        "mode": "full",
        "levels": [{"percent": 1.0, "exit_type": "atr", "params": {"mult": 4.0}}]
    }]
}
param_grid = generate_param_grid(param_ranges)

def extract_strategy_params(params, allowed_keys):
    return {k: v for k, v in params.items() if k in allowed_keys}

def extract_trades_from_logs(entry_log, exit_log):
    trades_list = []

    for i in range(min(len(entry_log), len(exit_log))):
        entry = entry_log[i]
        exit = exit_log[i]

        entry_price = entry.get("price")
        exit_price = exit.get("price")
        size = entry.get("size", 1)  # по умолчанию 1
        commission = COMMISSION_MODEL * (entry_price + exit_price) * size

        pnl = (exit_price - entry_price) * size
        pnl_comm = pnl - commission

        duration_sec = (
            (exit.get("datetime") - entry.get("datetime")).total_seconds()
            if entry.get("datetime") and exit.get("datetime")
            else None
        )

        trades_list.append({
            "entry_datetime": entry.get("datetime"),
            "entry_price": entry_price,
            "exit_datetime": exit.get("datetime"),
            "exit_price": exit_price,
            "size": size,
            "pnl": pnl,
            "pnl_comm": pnl_comm,
            "entry_reason": entry.get("reason"),
            "exit_reason": exit.get("reason"),
            "entry_rsi": entry.get("rsi"),
            "exit_rsi": exit.get("rsi"),
            "entry_atr": entry.get("atr"),
            "exit_atr": exit.get("atr"),
            "strategy_id": entry.get("strategy_id"),
            "symbol": entry.get("symbol"),
            "timeframe": entry.get("timeframe"),
            "duration_sec": duration_sec
        })

    df = pd.DataFrame(trades_list)

    # Гарантируем наличие всех столбцов
    expected_columns = [
        "entry_datetime", "entry_price", "exit_datetime", "exit_price", "size",
        "pnl", "pnl_comm", "entry_reason", "exit_reason", "entry_rsi", "exit_rsi",
        "entry_atr", "exit_atr", "strategy_id", "symbol", "timeframe", "duration_sec"
    ]
    for col in expected_columns:
        if col not in df.columns:
            df[col] = None

    return df

def run():
    indicators_used = SuperStrategy.params.indicators
     
    market_data = load_market_data(SYMBOLS, TIMEFRAMES, start_date=START_DATE, end_date=END_DATE)
    all_combos = list(product(SYMBOLS, TIMEFRAMES, param_grid))

    for symbol, tf, params in track(all_combos, description="[cyan]▶️ Общий прогон параметров[/cyan]"):
        df = market_data.get(symbol, {}).get(tf)
        if df is None or df.empty:
            console.print(f"[red]❌ Нет данных для {symbol} {tf}[/red]")
            continue

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        strategy_param_keys = SuperStrategy.params._getkeys()

        strategy_only_params = {k: params[k] for k in strategy_param_keys if k in params}
        strategy_id = hashlib.md5(str(dict(sorted(strategy_only_params.items()))).encode()).hexdigest()[:8]

        params.update({
            "indicators": indicators_used,
            "run_id": run_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "timeframe": tf
        })

        strategy_only_params = {k: params[k] for k in strategy_param_keys}
        strategy_params = extract_strategy_params(params, strategy_param_keys)
        df = apply_indicators(df, strategy_params)

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addstrategy(SuperStrategy, **strategy_params)
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.broker.setcash(INITIAL_CASH)
        cerebro.broker.set_slippage_perc(perc=SLIPPAGE)
        cerebro.broker.setcommission(commission=COMMISSION_MODEL, leverage=1)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')

        results = cerebro.run()
        strat = results[0]
        trade_analysis = strat.analyzers.trade_analyzer.get_analysis()

        final_value = cerebro.broker.getvalue()
        growth = round((final_value - INITIAL_CASH) / INITIAL_CASH * 100, 2)

        metrics = {
            "strategy_id": strategy_id,
            "run_id": run_id,
            "symbol": symbol,
            "timeframe": tf,
            "Initial_portfolio_value": INITIAL_CASH,
            "Final_portfolio_value": round(final_value, 2),
            "Final_portfolio_growth_percent": growth,
            "Total_trades": trade_analysis.total.closed if trade_analysis.total else 0,
            "Winning_trades": trade_analysis.won.total if trade_analysis.won else 0,
            "Losing_trades": trade_analysis.lost.total if trade_analysis.lost else 0,
            "Net_PnL": round(trade_analysis.pnl.net.total, 2) if trade_analysis.pnl else 0,
            "Average_Win_pnl": round(trade_analysis.won.pnl.average, 2) if trade_analysis.won.pnl else 0,
            "Average_Loss_pnl": round(trade_analysis.lost.pnl.average, 2) if trade_analysis.lost.pnl else 0
        }

        result_path = generate_result_path(symbol, tf, strategy_only_params)
        save_params(result_path, {**params, "start_date": START_DATE, "end_date": END_DATE})

        trades_df = extract_trades_from_logs(strat.entry_log, strat.exit_log)

        if not trades_df.empty:
            save_trades_full(result_path, trades_df)
        else:
            console.print(f"[red]❌ trades_full.csv пустой для {symbol} {tf}[/red]")

        if not trades_df.empty:
            profit_sum = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
            loss_sum = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
            profit_factor = profit_sum / loss_sum if loss_sum > 0 else float("inf")
            win_rate = (trades_df["pnl"] > 0).mean()
            loss_rate = (trades_df["pnl"] < 0).mean()
            avg_size = trades_df["size"].mean()
            avg_pnl_comm = trades_df["pnl_comm"].mean()
            duration = trades_df["duration_sec"]

            metrics.update({
                "Win_rate": round(win_rate, 4),
                "Loss_rate": round(loss_rate, 4),
                "Profit_factor": round(profit_factor, 4),
                "Avg_trade_size": round(avg_size, 2),
                "Avg_pnl_comm": round(avg_pnl_comm, 2),
                "Duration_avg_sec": round(duration.mean(), 2),
                "Duration_max_sec": round(duration.max(), 2),
                "Duration_min_sec": round(duration.min(), 2)
            })

            agg_trades = pd.DataFrame([
                ["total_closed", len(trades_df)],
                ["avg_pnl", trades_df["pnl"].mean()],
                ["avg_pnl_comm", avg_pnl_comm],
                ["avg_size", avg_size],
                ["win_rate", win_rate],
                ["loss_rate", loss_rate],
                ["profit_factor", profit_factor]
            ], columns=["metric", "value"])
            save_trades(result_path, agg_trades)

        save_metrics(result_path, metrics)

        equity_df = pd.DataFrame(strat.equity_curve, columns=["date", "equity"])
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df.set_index("date", inplace=True)
        save_equity_curve(result_path, equity_df)
        save_equity_plot_png(result_path, equity_df)
        save_entry_log(result_path, strat.entry_log)
        save_exit_log(result_path, strat.exit_log)

        qs.reports.html(
            returns=equity_df["equity"],
            title=f"{symbol} {tf} | {strategy_id}",
            output=result_path / f"{result_path.name}_quantstats.html",
            download=False
        )

        indicators = {}
        for key in ["rsi", "atr", "shandeller_exit", "ema", "kama"]:
            if key in df.columns:
                indicators[key.upper()] = df[key]

        plot_strategy_chart(
            df=df,
            entry_log=strat.entry_log,
            exit_log=strat.exit_log,
            indicators=indicators,
            save_path=result_path / f"{result_path.name}_strategy_chart.html"
        )

if __name__ == "__main__":
    run()
    console.print("\n[bold green]✅ Все прогоны завершены.[/bold green]")

