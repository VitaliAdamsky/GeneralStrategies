import matplotlib
matplotlib.use("Agg")

import backtrader as bt
import pandas as pd
from datetime import datetime, timedelta
from itertools import product
from rich.console import Console
from rich.progress import track
import quantstats as qs
from pathlib import Path
import json
import ccxt
import time
import shutil
import math

# --- Вспомогательные функции ---

def load_market_data(symbols, timeframes, start_date, end_date):
    console.print("[bold green]Загрузка реальных рыночных данных с Binance...[/bold green]")
    exchange = ccxt.binance()
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000) - 100 * 24 * 60 * 60 * 1000 # Загружаем на 100 дней раньше для индикаторов
    data = {}
    for symbol in track(symbols, description="[cyan]Загрузка активов...[/cyan]"):
        data[symbol] = {}
        for tf in track(timeframes, description=f"[green]Загрузка {symbol} TFs...[/green]", leave=False):
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, since=start_ts, limit=5000)
                if not ohlcv: continue
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('datetime', inplace=True)
                
                df_final = df[df.index >= pd.to_datetime(start_date)]
                df_final = df_final[df_final.index <= pd.to_datetime(end_date)]
                
                data[symbol][tf] = df_final[['open', 'high', 'low', 'close', 'volume']]
                time.sleep(0.5)
            except Exception as e:
                console.print(f"[bold red]❌ Ошибка при загрузке {symbol} {tf}: {e}[/bold red]")
    return data

def generate_result_path(symbol, tf, base_dir):
    path = base_dir / symbol / tf
    path.mkdir(parents=True, exist_ok=True)
    return path

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, default=str)

# --- Пользовательский индикатор ---

class GaussianFilter(bt.Indicator):
    lines = ('gf',)
    params = (('period', 30),)
    def __init__(self):
        self.addminperiod(self.p.period)
        self.weights = []
        sum_weights = 0
        for i in range(self.p.period):
            g = math.exp(-((i - (self.p.period - 1) / 2) ** 2) / (2 * (self.p.period / 6) ** 2))
            self.weights.insert(0, g)
            sum_weights += g
        self.weights = [w / sum_weights for w in self.weights]
    def next(self):
        value = 0
        for i in range(self.p.period):
            value += self.data.close[-i] * self.weights[i]
        self.lines.gf[0] = value

# --- НОВАЯ СТРАТЕГИЯ: "Канал в канале" ---

class DualGaussianStrategy(bt.Strategy):
    params = (
        ('slow_period', 100), ('fast_period', 30),
        ('atr_period', 20), ('atr_mult', 1.5)
    )

    def __init__(self):
        # Медленный канал (только центральная линия) для определения тренда
        self.slow_gauss = GaussianFilter(self.data.close, period=self.p.slow_period)
        
        # Быстрый канал для входов и выходов
        self.fast_gauss = GaussianFilter(self.data.close, period=self.p.fast_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.fast_upper = self.fast_gauss + self.atr * self.p.atr_mult
        self.fast_lower = self.fast_gauss - self.atr * self.p.atr_mult

        self.equity_curve = []

    def next(self):
        self.equity_curve.append((self.datas[0].datetime.datetime(0), self.broker.getvalue()))

        # --- Логика выхода ---
        if self.position:
            is_long = self.position.size > 0
            # Stop Loss
            if (is_long and self.data.close[0] < self.slow_gauss[0]) or \
               (not is_long and self.data.close[0] > self.slow_gauss[0]):
                self.close()
            # Take Profit
            elif (is_long and self.data.close[0] > self.fast_upper[0]) or \
                 (not is_long and self.data.close[0] < self.fast_lower[0]):
                self.close()
            return

        # --- Логика входа ---
        is_uptrend = self.data.close[0] > self.slow_gauss[0]
        
        # Вход в Лонг: глобальный аптренд И цена коснулась нижней границы быстрого канала
        if is_uptrend and self.data.close[0] < self.fast_lower[0]:
            self.buy()
        
        # Вход в Шорт: глобальный даунтренд И цена коснулась верхней границы быстрого канала
        elif not is_uptrend and self.data.close[0] > self.fast_upper[0]:
            self.sell()

# --- Основной скрипт ---

console = Console()
INITIAL_CASH = 100000

def run():
    results_dir = Path("results_dual_gaussian")
    if results_dir.exists():
        console.print(f"[bold yellow]🗑️  Очистка старых результатов из папки: {results_dir}[/bold yellow]")
        shutil.rmtree(results_dir)

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    timeframes = ["4H", "8H", "12H", "1D"]
    end_date_dt = datetime.now()
    start_date_dt = end_date_dt - timedelta(days=365)
    start_date = start_date_dt.strftime("%Y-%m-%d")
    end_date = end_date_dt.strftime("%Y-%m-%d")
    
    console.print(f"[bold]🚀 Запуск теста 'Канал в канале'[/bold]")
    console.print(f"Период: [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]")

    market_data = load_market_data(symbols, timeframes, start_date, end_date)
    
    for symbol, tf in track(list(product(symbols, timeframes)), description="[cyan]▶️  Тестирование активов[/cyan]"):
        df_trade = market_data.get(symbol, {}).get(tf)
        if df_trade is None or df_trade.empty or len(df_trade) < 150: continue

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addstrategy(DualGaussianStrategy)
        cerebro.adddata(bt.feeds.PandasData(dataname=df_trade))
        cerebro.broker.setcash(INITIAL_CASH)
        cerebro.broker.setcommission(commission=0.00055)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')

        results = cerebro.run()
        strat = results[0]
        trade_analysis = strat.analyzers.trade_analyzer.get_analysis()

        result_path = generate_result_path(symbol, tf, results_dir)
        
        final_value = cerebro.broker.getvalue()
        growth = (final_value - INITIAL_CASH) / INITIAL_CASH * 100
        total_trades = trade_analysis.total.closed if hasattr(trade_analysis, 'total') else 0
        winning_trades = trade_analysis.won.total if hasattr(trade_analysis, 'won') else 0
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0

        save_json(result_path / "metrics.json", {
            "Final_portfolio_growth_percent": round(growth, 2), "Total_trades": total_trades,
            "Win_Rate_percent": round(win_rate, 2)
        })
        
        if strat.equity_curve:
            equity_df = pd.DataFrame(strat.equity_curve, columns=["date", "equity"])
            equity_df.set_index(pd.to_datetime(equity_df["date"]), inplace=True)
            returns = equity_df["equity"].pct_change().dropna()
            if not returns.empty:
                 qs.reports.html(
                    returns=returns, title=f"{symbol} {tf} with Dual Gaussian Strategy",
                    output=str(result_path / "quantstats_report.html"),
                )

if __name__ == "__main__":
    run()
    console.print("\n[bold green]✅ Тестирование 'Канал в канале' завершено.[/bold green]")
