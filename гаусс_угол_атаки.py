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

# --- Новая Стратегия: "Угол Атаки" ---

class GaussianSlopeStrategy(bt.Strategy):
    params = (
        ('slow_period', 100), ('fast_period', 30),
        ('atr_period', 20), ('volume_period', 20),
        ('atr_z_period', 100), ('slope_period', 5),
        ('volume_mult', 1.5), ('sl_atr_mult', 1.0), ('tp_atr_mult', 2.0),
        ('atr_z_threshold', 0.0), # Порог для режима рынка
        ('slope_threshold', 0.00015) # --- НОВЫЙ ПОРОГ ДЛЯ УГЛА НАКЛОНА ---
    )

    def __init__(self):
        self.slow_gauss = GaussianFilter(self.data.close, period=self.p.slow_period)
        self.fast_gauss = GaussianFilter(self.data.close, period=self.p.fast_period)
        self.crossover = bt.ind.CrossOver(self.fast_gauss, self.slow_gauss)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.volume_sma = bt.ind.SMA(self.data.volume, period=self.p.volume_period)
        
        # Фильтр Режима Рынка
        atr_sma = bt.ind.SMA(self.atr, period=self.p.atr_z_period)
        atr_std = bt.ind.StdDev(self.atr, period=self.p.atr_z_period)
        safe_atr_std = bt.If(atr_std > 0, atr_std, 0.000001)
        self.atr_zscore = (self.atr - atr_sma) / safe_atr_std
        
        # --- НОВЫЙ ФИЛЬТР: "Угол Атаки" (Наклон) ---
        # Рассчитываем наклон медленного гаусса и нормализуем его по цене
        raw_slope = self.slow_gauss - self.slow_gauss(-self.p.slope_period)
        self.normalized_slope = raw_slope / self.data.close

        self.equity_curve = []
        self.order = None

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]: return
        self.order = None

    def next(self):
        self.equity_curve.append((self.datas[0].datetime.datetime(0), self.broker.getvalue()))
        if self.order or self.position: return

        # Фильтр 1: Режим рынка (должен быть трендовым)
        if self.atr_zscore[0] <= self.p.atr_z_threshold: return
        
        # --- Логика Входа в Лонг ---
        if self.crossover[0] > 0:
            # Фильтр 2: "Угол Атаки" (тренд должен быть сильным)
            if self.normalized_slope[0] > self.p.slope_threshold:
                # Фильтр 3: Объем
                if self.data.volume[0] > self.volume_sma[0] * self.p.volume_mult:
                    sl_price = self.data.close[0] - self.atr[0] * self.p.sl_atr_mult
                    tp_price = self.data.close[0] + self.atr[0] * self.p.tp_atr_mult
                    self.order = self.buy(exectype=bt.Order.Limit, price=tp_price, transmit=False)
                    self.sell(exectype=bt.Order.Stop, price=sl_price, parent=self.order, transmit=True)
                    
        # --- Логика Входа в Шорт ---
        elif self.crossover[0] < 0:
            # Фильтр 2: "Угол Атаки"
            if self.normalized_slope[0] < -self.p.slope_threshold:
                 # Фильтр 3: Объем
                if self.data.volume[0] > self.volume_sma[0] * self.p.volume_mult:
                    sl_price = self.data.close[0] + self.atr[0] * self.p.sl_atr_mult
                    tp_price = self.data.close[0] - self.atr[0] * self.p.tp_atr_mult
                    self.order = self.sell(exectype=bt.Order.Limit, price=tp_price, transmit=False)
                    self.buy(exectype=bt.Order.Stop, price=sl_price, parent=self.order, transmit=True)

# --- Основной скрипт ---
console = Console()
INITIAL_CASH = 100000

def run():
    results_dir = Path("results_gaussian_slope")
    if results_dir.exists():
        console.print(f"[bold yellow]🗑️  Очистка старых результатов из папки: {results_dir}[/bold yellow]")
        shutil.rmtree(results_dir)

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    timeframes = ["4H", "8H", "12H", "1D"]
    end_date_dt = datetime.now()
    start_date_dt = end_date_dt - timedelta(days=365)
    start_date = start_date_dt.strftime("%Y-%m-%d")
    end_date = end_date_dt.strftime("%Y-%m-%d")
    
    console.print(f"[bold]🚀 Запуск теста 'Угол Атаки'[/bold]")
    console.print(f"Период: [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]")

    market_data = load_market_data(symbols, timeframes, start_date, end_date)
    
    for symbol, tf in track(list(product(symbols, timeframes)), description="[cyan]▶️  Тестирование активов[/cyan]"):
        df_trade = market_data.get(symbol, {}).get(tf)
        if df_trade is None or df_trade.empty or len(df_trade) < 200: continue

        cerebro = bt.Cero(stdstats=False)
        cerebro.addstrategy(GaussianSlopeStrategy)
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
                    returns=returns, title=f"{symbol} {tf} with Gaussian Slope Strategy",
                    output=str(result_path / "quantstats_report.html"),
                )

if __name__ == "__main__":
    run()
    console.print("\n[bold green]✅ Тестирование 'Угла Атаки' завершено.[/bold green]")
