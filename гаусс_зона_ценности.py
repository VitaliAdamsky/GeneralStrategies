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
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000) - 200 * 24 * 60 * 60 * 1000
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

# --- Пользовательские Индикаторы ---

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

# --- Новая Стратегия: Гибрид Price Action и Гаусса ---

class GaussianPAStrategy(bt.Strategy):
    params = (
        ('slow_period', 100), ('atr_period_slow', 20), ('atr_mult_slow', 1.5),
        ('volume_period', 10),
        ('sl_atr_mult', 1.2), ('tp_atr_mult', 2.4) # Risk/Reward ~ 1:2
    )

    def __init__(self):
        # Медленный канал для определения "реки" и "зоны ценности"
        self.slow_gauss = GaussianFilter(self.data.close, period=self.p.slow_period)
        self.atr_slow = bt.ind.ATR(self.data, period=self.p.atr_period_slow)
        self.slow_upper = self.slow_gauss + self.atr_slow * self.p.atr_mult_slow
        self.slow_lower = self.slow_gauss - self.atr_slow * self.p.atr_mult_slow
        
        # Индикаторы для фильтра
        self.volume_sma = bt.ind.SMA(self.data.volume, period=self.p.volume_period)
        
        # Индикаторы для Price Action (свечные паттерны)
        self.hammer = bt.talib.CDLHAMMER(self.data.open, self.data.high, self.data.low, self.data.close)
        self.shooting_star = bt.talib.CDLSHOOTINGSTAR(self.data.open, self.data.high, self.data.low, self.data.close)

        self.equity_curve = []
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        self.order = None

    def next(self):
        self.equity_curve.append((self.datas[0].datetime.datetime(0), self.broker.getvalue()))
        if self.order or self.position: return

        is_uptrend = self.data.close[0] > self.slow_gauss[0]
        
        # --- Логика Входа в Лонг ---
        if is_uptrend:
            # 1. Цена в "зоне ценности" для покупки (нижняя половина канала)
            if self.data.close[0] < self.slow_gauss[0] and self.data.low[0] > self.slow_lower[0]:
                # 2. Появился бычий паттерн "Молот"
                if self.hammer[0] > 0:
                    # 3. Паттерн подтвержден объемом
                    if self.data.volume[0] > self.volume_sma[0]:
                        sl = self.data.low[0] - self.atr_slow[0] * 0.2 # SL под минимум свечи
                        tp = self.data.close[0] + (self.data.close[0] - sl) * 2.0 # TP = 2 * Risk
                        self.buy(exectype=bt.Order.Market)
                        self.sell(exectype=bt.Order.Stop, price=sl)
                        self.sell(exectype=bt.Order.Limit, price=tp)

        # --- Логика Входа в Шорт ---
        else: # is_downtrend
            # 1. Цена в "зоне ценности" для продажи (верхняя половина канала)
            if self.data.close[0] > self.slow_gauss[0] and self.data.high[0] < self.slow_upper[0]:
                # 2. Появился медвежий паттерн "Падающая звезда"
                if self.shooting_star[0] != 0:
                    # 3. Паттерн подтвержден объемом
                    if self.data.volume[0] > self.volume_sma[0]:
                        sl = self.data.high[0] + self.atr_slow[0] * 0.2 # SL над максимум свечи
                        tp = self.data.close[0] - (sl - self.data.close[0]) * 2.0 # TP = 2 * Risk
                        self.sell(exectype=bt.Order.Market)
                        self.buy(exectype=bt.Order.Stop, price=sl)
                        self.buy(exectype=bt.Order.Limit, price=tp)


# --- Основной скрипт ---
console = Console()
INITIAL_CASH = 100000

def run():
    results_dir = Path("results_gaussian_pa")
    if results_dir.exists():
        console.print(f"[bold yellow]🗑️  Очистка старых результатов из папки: {results_dir}[/bold yellow]")
        shutil.rmtree(results_dir)

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    timeframes = ["4H", "8H", "12H", "1D"]
    end_date_dt = datetime.now()
    start_date_dt = end_date_dt - timedelta(days=365)
    start_date = start_date_dt.strftime("%Y-%m-%d")
    end_date = end_date_dt.strftime("%Y-%m-%d")
    
    console.print(f"[bold]🚀 Запуск теста 'Гибрид Price Action и Гаусса'[/bold]")
    console.print(f"Период: [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]")

    market_data = load_market_data(symbols, timeframes, start_date, end_date)
    
    for symbol, tf in track(list(product(symbols, timeframes)), description="[cyan]▶️  Тестирование активов[/cyan]"):
        df_trade = market_data.get(symbol, {}).get(tf)
        if df_trade is None or df_trade.empty or len(df_trade) < 200: continue

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addstrategy(GaussianPAStrategy)
        cerebro.adddata(bt.feeds.PandasData(datename=df_trade))
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
                    returns=returns, title=f"{symbol} {tf} with Gaussian PA Strategy",
                    output=str(result_path / "quantstats_report.html"),
                )

if __name__ == "__main__":
    run()
    console.print("\n[bold green]✅ Тестирование 'Гибрида Price Action' завершено.[/bold green]")
