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

def load_market_data_with_vwap_filter(symbols, timeframes, start_date, end_date):
    """
    Загружает данные, добавляя к ним фильтр по наклону VWAP со старшего ТФ.
    """
    console.print("[bold green]Загрузка данных и расчет фильтра VWAP...[/bold green]")
    exchange = ccxt.binance()
    start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000) - 100 * 7 * 24 * 60 * 60 * 1000 # Загружаем на 100 недель раньше для VWAP
    data = {}

    for symbol in track(symbols, description="[cyan]Обработка активов...[/cyan]"):
        data[symbol] = {}
        # 1. Загружаем и рассчитываем недельный VWAP
        try:
            ohlcv_w = exchange.fetch_ohlcv(symbol, '1w', since=start_ts, limit=2000)
            if not ohlcv_w: continue
            df_w = pd.DataFrame(ohlcv_w, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_w['datetime'] = pd.to_datetime(df_w['timestamp'], unit='ms')
            
            # Расчет VWAP
            typical_price = (df_w['high'] + df_w['low'] + df_w['close']) / 3
            vol_price = typical_price * df_w['volume']
            df_w['vwap'] = vol_price.rolling(window=100).sum() / df_w['volume'].rolling(window=100).sum()
            df_w['vwap_slope'] = df_w['vwap'].diff()
            df_w['is_uptrend'] = df_w['vwap_slope'] > 0
            
            df_w = df_w[['datetime', 'is_uptrend']].dropna()
        except Exception as e:
            console.print(f"[bold red]❌ Не удалось рассчитать VWAP для {symbol}: {e}[/bold red]")
            continue

        # 2. Загружаем младшие ТФ и добавляем фильтр
        for tf in timeframes:
            try:
                ohlcv = exchange.fetch_ohlcv(symbol, tf, since=start_ts, limit=5000)
                if not ohlcv: continue
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')

                # Добавляем данные о тренде с недельного графика
                merged_df = pd.merge_asof(df.sort_values('datetime'), df_w, on='datetime', direction='backward')
                merged_df.set_index('datetime', inplace=True)
                
                final_df = merged_df[merged_df.index >= pd.to_datetime(start_date)]
                final_df = final_df[final_df.index <= pd.to_datetime(end_date)]
                
                data[symbol][tf] = final_df[['open', 'high', 'low', 'close', 'volume', 'is_uptrend']].dropna()

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

# --- НОВАЯ СТРАТЕГИЯ: Возврат к среднему с тройным фильтром ---

class GaussianMeanReversionStrategy(bt.Strategy):
    params = (
        ('gauss_period', 30), ('atr_period', 20), ('z_threshold', 2.0),
        ('volume_period', 10), ('volume_mult', 1.5)
    )

    def __init__(self):
        self.gauss_ma = GaussianFilter(self.data.close, period=self.p.gauss_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        
        # Наш кастомный Z-Score
        self.custom_z = (self.data.close - self.gauss_ma) / self.atr
        
        self.volume_sma = bt.ind.SMA(self.data.volume, period=self.p.volume_period)
        
        # Фильтр тренда (уже в данных)
        self.is_uptrend = self.data.is_uptrend

        self.equity_curve = []

    def next(self):
        self.equity_curve.append((self.datas[0].datetime.datetime(0), self.broker.getvalue()))

        # --- Логика выхода ---
        if self.position:
            is_long = self.position.size > 0
            # Выход, если цена пересекла центральную линию
            if (is_long and self.data.close[0] >= self.gauss_ma[0]) or \
               (not is_long and self.data.close[0] <= self.gauss_ma[0]):
                self.close()
            return

        # --- Логика входа ---
        volume_ok = self.data.volume[0] > (self.volume_sma[0] * self.p.volume_mult)

        # Лонг, если: аптренд, выброс вниз и всплеск объема
        if self.is_uptrend[0] and self.custom_z[0] < -self.p.z_threshold and volume_ok:
            self.buy()
        # Шорт, если: даунтренд, выброс вверх и всплеск объема
        elif not self.is_uptrend[0] and self.custom_z[0] > self.p.z_threshold and volume_ok:
            self.sell()

# --- Основной скрипт ---

console = Console()
INITIAL_CASH = 100000

def run():
    results_dir = Path("results_gaussian_reversion")
    if results_dir.exists():
        console.print(f"[bold yellow]🗑️  Очистка старых результатов из папки: {results_dir}[/bold yellow]")
        shutil.rmtree(results_dir)

    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    timeframes = ["4H", "8H", "12H", "1D"]
    end_date_dt = datetime.now()
    start_date_dt = end_date_dt - timedelta(days=365)
    start_date = start_date_dt.strftime("%Y-%m-%d")
    end_date = end_date_dt.strftime("%Y-%m-%d")
    
    console.print(f"[bold]🚀 Запуск теста возврата к среднему (Гаусс + Z-Score + VWAP + Volume)[/bold]")
    console.print(f"Период: [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]")

    market_data = load_market_data_with_vwap_filter(symbols, timeframes, start_date, end_date)
    
    for symbol, tf in track(list(product(symbols, timeframes)), description="[cyan]▶️  Тестирование активов[/cyan]"):
        df_trade = market_data.get(symbol, {}).get(tf)
        if df_trade is None or df_trade.empty or len(df_trade) < 150: continue

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addstrategy(GaussianMeanReversionStrategy)
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
                    returns=returns, title=f"{symbol} {tf} with Gaussian Mean Reversion",
                    output=str(result_path / "quantstats_report.html"),
                )

if __name__ == "__main__":
    run()
    console.print("\n[bold green]✅ Тестирование возврата к среднему завершено.[/bold green]")

