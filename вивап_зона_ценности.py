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

class RollingVWAP(bt.Indicator):
    lines = ('vwap',)
    params = (('period', 100),)
    def __init__(self):
        self.addminperiod(self.p.period)
        # Рассчитываем типичную цену, взвешенную по объему
        tpv = (self.data.high + self.data.low + self.data.close) / 3 * self.data.volume
        # Суммируем за период
        sum_tpv = bt.ind.SumN(tpv, period=self.p.period)
        sum_vol = bt.ind.SumN(self.data.volume, period=self.p.period)
        # Предотвращаем деление на ноль
        safe_sum_vol = bt.If(sum_vol > 0, sum_vol, 1)
        self.lines.vwap = sum_tpv / safe_sum_vol

# --- Новая Стратегия: Гибрид Price Action и VWAP ---

class VWAPPAStrategy(bt.Strategy):
    params = (
        ('vwap_period', 100), ('atr_period', 20), ('atr_mult', 1.5),
        ('volume_period', 10)
    )

    def __init__(self):
        # --- НОВЫЙ КАНАЛ НА ОСНОВЕ VWAP ---
        self.vwap = RollingVWAP(self.data, period=self.p.vwap_period)
        self.atr = bt.ind.ATR(self.data, period=self.p.atr_period)
        self.vwap_upper = self.vwap + self.atr * self.p.atr_mult
        self.vwap_lower = self.vwap - self.atr * self.p.atr_mult
        
        # Индикаторы для фильтра и сигналов
        self.volume_sma = bt.ind.SMA(self.data.volume, period=self.p.volume_period)
        self.hammer = bt.talib.CDLHAMMER(self.data.open, self.data.high, self.data.low, self.data.close)
        self.shooting_star = bt.talib.CDLSHOOTINGSTAR(self.data.open, self.data.high, self.data.low, self.data.close)

        self.equity_curve = []
        self.order_bracket = [] # Для хранения стопа и тейка

    def notify_order(self, order):
        if order.status in [order.Completed, order.Canceled, order.Margin, order.Rejected]:
            self.order_bracket = [] # Очищаем при закрытии/отмене

    def next(self):
        self.equity_curve.append((self.datas[0].datetime.datetime(0), self.broker.getvalue()))
        if self.position or self.order_bracket: return

        is_uptrend = self.data.close[0] > self.vwap[0]
        
        # --- Логика Входа в Лонг ---
        if is_uptrend:
            if self.data.close[0] < self.vwap[0] and self.data.low[0] > self.vwap_lower[0]:
                if self.hammer[0] > 0:
                    if self.data.volume[0] > self.volume_sma[0]:
                        entry_price = self.data.close[0]
                        sl_price = self.data.low[0] - self.atr[0] * 0.2
                        tp_price = entry_price + (entry_price - sl_price) * 2.0
                        self.order_bracket = self.buy_bracket(price=entry_price, stopprice=sl_price, limitprice=tp_price)

        # --- Логика Входа в Шорт ---
        else: # is_downtrend
            if self.data.close[0] > self.vwap[0] and self.data.high[0] < self.vwap_upper[0]:
                if self.shooting_star[0] != 0:
                    if self.data.volume[0] > self.volume_sma[0]:
                        entry_price = self.data.close[0]
                        sl_price = self.data.high[0] + self.atr[0] * 0.2
                        tp_price = entry_price - (sl_price - entry_price) * 2.0
                        self.order_bracket = self.sell_bracket(price=entry_price, stopprice=sl_price, limitprice=tp_price)

# --- Основной скрипт ---
console = Console()
INITIAL_CASH = 100000

def run():
    results_dir = Path("results_vwap_pa_high_vol")
    if results_dir.exists():
        console.print(f"[bold yellow]🗑️  Очистка старых результатов из папки: {results_dir}[/bold yellow]")
        shutil.rmtree(results_dir)

    # --- НОВЫЙ СПИСОК: ТОП-10 ПО ВОЛАТИЛЬНОСТИ ---
    symbols = [
        "DOGEUSDT", "SHIBUSDT", "PEPEUSDT", "WIFUSDT", "BONKUSDT", 
        "AVAXUSDT", "LINKUSDT", "ADAUSDT", "MATICUSDT", "INJUSDT"
    ]
    timeframes = ["4H", "8H", "12H", "1D"]
    end_date_dt = datetime.now()
    start_date_dt = end_date_dt - timedelta(days=365)
    start_date = start_date_dt.strftime("%Y-%m-%d")
    end_date = end_date_dt.strftime("%Y-%m-%d")
    
    console.print(f"[bold]🚀 Запуск стресс-теста 'Гибрид VWAP на волатильных активах'[/bold]")
    console.print(f"Период: [cyan]{start_date}[/cyan] to [cyan]{end_date}[/cyan]")

    market_data = load_market_data(symbols, timeframes, start_date, end_date)
    
    for symbol, tf in track(list(product(symbols, timeframes)), description="[cyan]▶️  Тестирование активов[/cyan]"):
        df_trade = market_data.get(symbol, {}).get(tf)
        if df_trade is None or df_trade.empty or len(df_trade) < 200: continue

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addstrategy(VWAPPAStrategy)
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
                    returns=returns, title=f"{symbol} {tf} with VWAP PA Strategy",
                    output=str(result_path / "quantstats_report.html"),
                )

if __name__ == "__main__":
    run()
    console.print("\n[bold green]✅ Стресс-тест 'Гибрида VWAP' завершен.[/bold green]")
