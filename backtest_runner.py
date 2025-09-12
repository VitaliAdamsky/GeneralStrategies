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
    save_exit_log
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

def extract_trades(trade_analysis):
    trades = trade_analysis.get("trades", {})
    trades_list = []
    for t in trades.values():
        trades_list.append({
            'entry_datetime': t.dtopen,
            'entry_price': t.price,
            'exit_datetime': t.dtclose,
            'exit_price': t.exitprice,
            'size': t.size,
            'pnl': t.pnl,
            'pnl_comm': t.pnlcomm
        })
    return pd.DataFrame(trades_list)

def run():
    market_data = load_market_data(SYMBOLS, TIMEFRAMES, start_date=START_DATE, end_date=END_DATE)
    all_combos = list(product(SYMBOLS, TIMEFRAMES, param_grid))

    for symbol, tf, params in track(all_combos, description="[cyan]▶️ Общий прогон параметров[/cyan]"):
        df = market_data.get(symbol, {}).get(tf)
        if df is None or df.empty:
            console.print(f"[red]❌ Нет данных для {symbol} {tf}[/red]")
            continue

        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        strategy_param_keys = SuperStrategy.params._getkeys()
        strategy_only_params = {k: params[k] for k in strategy_param_keys}
        strategy_id = hashlib.md5(str(strategy_only_params).encode()).hexdigest()[:8]
        params.update({"run_id": run_id, "strategy_id": strategy_id})

        strategy_params = extract_strategy_params(params, strategy_param_keys)

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
        save_metrics(result_path, metrics)

        trades_df = extract_trades(trade_analysis)
        save_trades_full(result_path, trades_df)

        agg_trades = pd.DataFrame(columns=["metric", "value"])
        if not trades_df.empty:
            profit_sum = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
            loss_sum = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
            profit_factor = profit_sum / loss_sum if loss_sum > 0 else float("inf")

            agg_trades = pd.DataFrame([
                ["total_closed", len(trades_df)],
                ["avg_pnl", trades_df["pnl"].mean()],
                ["avg_pnl_comm", trades_df["pnl_comm"].mean()],
                ["avg_size", trades_df["size"].mean()],
                ["win_rate", (trades_df["pnl"] > 0).mean()],
                ["loss_rate", (trades_df["pnl"] < 0).mean()],
                ["profit_factor", profit_factor]
            ], columns=["metric", "value"])

        save_trades(result_path, agg_trades)

        equity_df = pd.DataFrame(strat.equity_curve, columns=["date", "equity"])
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df.set_index("date", inplace=True)
        save_equity_curve(result_path, equity_df)
        save_exit_log(result_path, strat.exit_log)

        qs.reports.html(
            returns=equity_df["equity"],
            title=f"{symbol} {tf} | {strategy_id}",
            output=result_path / f"{result_path.name}_quantstats.html",
            download=False
        )

if __name__ == "__main__":
    run()
    console.print("\n[bold green]✅ Все прогоны завершены.[/bold green]")
