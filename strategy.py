import backtrader as bt
import pandas as pd
from core import (
    load_market_data,
    generate_param_grid,
    generate_result_path,
    save_params,
    save_metrics,
    save_trades,
    save_trades_full,
    save_equity_curve,
    save_exit_log,
    evaluate_exit_levels
)

# === Конфигурация ===
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
TIMEFRAMES = ["1D", "12H"]
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"
INITIAL_CASH = 100000

# === Параметры стратегии (всегда списки!)
param_ranges = {
    "rsi_period": [14],
    "atr_period": [14],
    "take_profit": [{
        "mode": "full",
        "levels": [
            {
                "percent": 1.0,
                "exit_type": "atr",
                "params": {"mult": 4.0}
            }
        ]
    }]
}
param_grid = generate_param_grid(param_ranges)

# === Стратегия ===
class RsiAtrStrategy(bt.Strategy):
    params = dict(
        rsi_period=14,
        atr_period=14,
        take_profit=None
    )

    def __init__(self):
        self.rsi = bt.indicators.RSI_SMA(self.data.close, period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        self.ema = bt.indicators.EMA(self.data.close, period=20)
        self.kama = bt.indicators.KAMA(self.data.close, period=20)

        self.entry_price = None
        self.position_size = 0
        self.exit_plan = self.p.take_profit["levels"]
        self.exit_mode = self.p.take_profit["mode"]
        self.trade_log = []
        self.exit_log = []
        self.equity_curve = []

    def next(self):
        self.equity_curve.append([self.data.datetime.datetime(0), self.broker.getvalue()])

        if not self.position:
            if self.rsi[0] < 30:
                self.entry_price = self.data.close[0]
                self.position_size = self.broker.getvalue() / self.data.close[0]
                self.buy(size=self.position_size)
        else:
            context = {
                "entry_price": self.entry_price,
                "position_size": self.position_size,
                "current_price": self.data.close[0],
                "atr": self.atr[0],
                "ema": self.ema[0],
                "kama": self.kama[0],
                "prev_ema": self.ema[-1],
                "prev_kama": self.kama[-1],
                "highest_close": max(self.data.close.get(size=20)),
                "lowest_close": min(self.data.close.get(size=20))
            }

            exit_levels = evaluate_exit_levels(self.exit_plan, context)

            if exit_levels:
                exit = exit_levels[0]  # mode: full → один выход
                self.close()
                self.exit_log.append({
                    "timestamp": str(self.data.datetime.datetime(0)),
                    "price": self.data.close[0],
                    "percent": exit["percent"],
                    "exit_type": exit["exit_type"],
                    "reason": exit["reason"]
                })
                self.trade_log.append([
                    self.entry_price,
                    self.data.close[0],
                    exit["exit_type"],
                    exit["percent"],
                    self.data.datetime.datetime(0)
                ])

# === Загрузка данных ===
market_data = load_market_data(SYMBOLS, TIMEFRAMES, start_date=START_DATE, end_date=END_DATE)

# === Прогон по всем комбо ===
for symbol in SYMBOLS:
    for tf in TIMEFRAMES:
        df = market_data.get(symbol, {}).get(tf)
        if df is None or df.empty:
            print(f"[red]❌ Нет данных для {symbol} {tf}[/red]")
            continue

        for params in param_grid:
            cerebro = bt.Cerebro()
            cerebro.addstrategy(RsiAtrStrategy, **params)
            data = bt.feeds.PandasData(dataname=df)
            cerebro.adddata(data)
            cerebro.broker.setcash(INITIAL_CASH)
            cerebro.broker.setcommission(commission=0.001)

            results = cerebro.run()
            strat = results[0]

            final_value = cerebro.broker.getvalue()
            growth = round((final_value - INITIAL_CASH) / INITIAL_CASH * 100, 2)
            metrics = {
                "Initial_portfolio_value": INITIAL_CASH,
                "Final_portfolio_value": round(final_value, 2),
                "Final_portfolio_growth_percent": growth,
                "Total_trades": len(strat.trade_log),
                "ATR_exits": sum(1 for t in strat.trade_log if t[2] == "atr"),
                "Chandelier_exits": sum(1 for t in strat.trade_log if t[2] == "chandelier")
            }

            result_path = generate_result_path(symbol, tf, params)
            save_params(result_path, {**params, "start_date": START_DATE, "end_date": END_DATE})
            save_metrics(result_path, metrics)

            trades_df = pd.DataFrame(strat.trade_log, columns=[
                "entry_price", "exit_price", "exit_type", "percent_closed", "exit_time"
            ])

            # === Агрегированные сделки
            agg_trades = pd.DataFrame([
                ["total_closed", len(trades_df)],
                ["avg_exit_price", trades_df["exit_price"].mean()],
                ["avg_percent_closed", trades_df["percent_closed"].mean()],
                ["take_hits", (trades_df["exit_type"] == "atr").sum()],
                ["chandelier_hits", (trades_df["exit_type"] == "chandelier").sum()]
            ], columns=["metric", "value"])
            save_trades(result_path, agg_trades)

            save_trades_full(result_path, trades_df)

            equity_df = pd.DataFrame(strat.equity_curve, columns=["date", "equity"])
            equity_df["date"] = pd.to_datetime(equity_df["date"])
            equity_df.set_index("date", inplace=True)
            save_equity_curve(result_path, equity_df)

            save_exit_log(result_path, strat.exit_log)
