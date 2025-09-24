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
from multiprocessing import Pool, cpu_count
import traceback
import copy # Import copy module
from pathlib import Path # Импортируем Path

# Предполагается, что ваши модули core и strategies находятся в том же каталоге или в PYTHONPATH
from core import (
    load_market_data,
    generate_param_grid,
    # generate_result_path, # Убираем импорт, так как определяем функцию локально
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
from core.enums import Timeframes
from strategies import SuperStrategy

# --- Конфигурация ---
console = Console()
SLIPPAGE = 0.0005
COMMISSION_MODEL = 0.00055
START_DATE = "2023-01-01"
END_DATE = "2024-12-31"
INITIAL_CASH = 100000

# --- Сетка параметров ---
param_ranges = {
    "symbol": ["BTCUSDT", "ETHUSDT"],
    "timeframe": [Timeframes.D_1, Timeframes.H_12],
    "indicators": [{"name": "RSI", "len": [10, 14]}, {"name": "ATR", "len": [10, 14]}],
    "take_profit": [{
        "mode": "full",
        "levels": [{"percent": 1.0, "exit_type": "atr", "params": {"mult": 4.0}}]
    }]
}

# --- НОВАЯ ЛОКАЛЬНАЯ ФУНКЦИЯ ДЛЯ ГЕНЕРАЦИИ ПУТИ ---
def generate_result_path(symbol: str, timeframe: str, run_id: str, strategy_id: str) -> Path:
    """
    Генерирует уникальный, датированный путь для результатов бэктеста.
    Формат: results/SYMBOL/TIMEFRAME/YYYY_MM_DD_HH_MM_SS_strategyid/
    """
    dt = datetime.strptime(run_id, "%Y%m%d_%H%M%S_%f")
    timestamp = dt.strftime("%Y_%m_%d_%H_%M_%S")
    folder_name = f"{timestamp}_{strategy_id}"
    return Path("results") / symbol / timeframe / folder_name

# --- Вспомогательная функция для одного запуска бэктеста ---
def run_single_backtest(args):
    """
    Выполняет один бэктест для заданного набора параметров.
    """
    params, market_data = args
    symbol = params["symbol"]
    timeframe_enum = params["timeframe"]
    tf_value = timeframe_enum.value

    try:
        df = market_data.get(symbol, {}).get(tf_value)
        if df is None or df.empty:
            return (symbol, tf_value, "No Data", None)

        # --- Настройка ID и путей ---
        strategy_param_keys = SuperStrategy.params._getkeys()
        strategy_only_params = {k: v for k, v in params.items() if k in strategy_param_keys}
        
        # Исправляем неоднозначность при создании хэша
        params_for_hash = {
            **strategy_only_params,
            "symbol": symbol,
            "timeframe": tf_value, # Гарантированно перезаписываем enum строкой
        }
        strategy_id = hashlib.md5(str(dict(sorted(params_for_hash.items()))).encode()).hexdigest()[:8]
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        params.update({"run_id": run_id, "strategy_id": strategy_id})

        result_path = generate_result_path(symbol, tf_value, run_id, strategy_id)
        result_path.mkdir(parents=True, exist_ok=True)
        df = apply_indicators(df, params)

        # --- Настройка Cerebro ---
        # ИСПРАВЛЕНИЕ: Готовим параметры для стратегии, чтобы она тоже получала строку.
        # Это исправляет запись в "сырые" логи (entry/exit_log.json).
        params_for_strategy = copy.deepcopy(strategy_only_params)
        if 'timeframe' in params_for_strategy and isinstance(params_for_strategy['timeframe'], Timeframes):
            params_for_strategy['timeframe'] = params_for_strategy['timeframe'].value

        cerebro = bt.Cerebro(stdstats=False)
        cerebro.addstrategy(SuperStrategy, **params_for_strategy) # Используем очищенные параметры
        data = bt.feeds.PandasData(dataname=df)
        cerebro.adddata(data)
        cerebro.broker.setcash(INITIAL_CASH)
        cerebro.broker.set_slippage_perc(perc=SLIPPAGE)
        cerebro.broker.setcommission(commission=COMMISSION_MODEL, leverage=1)
        cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trade_analyzer')
        cerebro.addanalyzer(bt.analyzers.PyFolio, _name='pyfolio')

        # --- Запуск бэктеста ---
        results = cerebro.run()
        strat = results[0]
        
        # --- Анализ и сохранение ---
        trade_analysis = strat.analyzers.trade_analyzer.get_analysis()
        final_value = cerebro.broker.getvalue()
        growth = round((final_value - INITIAL_CASH) / INITIAL_CASH * 100, 2)

        metrics = {
            "strategy_id": strategy_id, "run_id": run_id, "symbol": symbol, "timeframe": tf_value,
            "initial_cash": INITIAL_CASH, "final_value": round(final_value, 2), "growth_pct": growth,
            "total_trades": trade_analysis.total.closed if trade_analysis.total else 0,
            "winning_trades": trade_analysis.won.total if trade_analysis.won else 0,
            "losing_trades": trade_analysis.lost.total if trade_analysis.lost else 0,
        }
        
        trades_df = extract_trades_from_logs(strat.entry_log, strat.exit_log)

        if not trades_df.empty:
            profit_sum = trades_df[trades_df["pnl"] > 0]["pnl"].sum()
            loss_sum = abs(trades_df[trades_df["pnl"] < 0]["pnl"].sum())
            profit_factor = profit_sum / loss_sum if loss_sum > 0 else float("inf")
            win_rate = (trades_df["pnl"] > 0).mean()
            metrics.update({
                "win_rate": round(win_rate, 4), "profit_factor": round(profit_factor, 4),
                "avg_pnl_comm": round(trades_df["pnl_comm"].mean(), 2),
            })

        # --- Сохранение артефактов ---
        params_to_save = copy.deepcopy(params)
        if 'timeframe' in params_to_save and isinstance(params_to_save['timeframe'], Timeframes):
            params_to_save['timeframe'] = params_to_save['timeframe'].value
        save_params(result_path, {**params_to_save, "start_date": START_DATE, "end_date": END_DATE})
        
        save_metrics(result_path, metrics)
        if not trades_df.empty:
            save_trades_full(result_path, trades_df)

        equity_df = pd.DataFrame(strat.equity_curve, columns=["date", "equity"])
        equity_df["date"] = pd.to_datetime(equity_df["date"])
        equity_df.set_index("date", inplace=True)
        save_equity_curve(result_path, equity_df)
        save_equity_plot_png(result_path, equity_df)
        save_entry_log(result_path, strat.entry_log)
        save_exit_log(result_path, strat.exit_log)

        qs.reports.html(
            returns=equity_df["equity"].pct_change().dropna(),
            title=f"{symbol} {tf_value} | {strategy_id}",
            output=result_path / f"{result_path.name}_quantstats.html",
        )

        indicators = {}
        for ind_cfg in params.get("indicators", []):
            name = ind_cfg.get("name", "").lower()
            if name in df.columns:
                indicators[name.upper()] = df[name]
        plot_strategy_chart(
            df=df, entry_log=strat.entry_log, exit_log=strat.exit_log,
            indicators=indicators, save_path=result_path / f"{result_path.name}_strategy_chart.html"
        )
        return (symbol, tf_value, "Success", result_path)

    except Exception as e:
        error_info = traceback.format_exc()
        console.print(f"[bold red]Ошибка при обработке {symbol} {tf_value}: {e}[/bold red]")
        console.print(error_info)
        return (symbol, tf_value, "Error", str(e))

def extract_trades_from_logs(entry_log, exit_log):
    trades_list = []
    for i in range(min(len(entry_log), len(exit_log))):
        entry, exit_ = entry_log[i], exit_log[i]
        entry_price, exit_price = entry.get("price"), exit_.get("price")
        size = entry.get("size", 1)
        commission = COMMISSION_MODEL * (entry_price + exit_price) * size
        pnl = (exit_price - entry_price) * size
        duration_sec = (exit_.get("datetime") - entry.get("datetime")).total_seconds() if entry.get("datetime") and exit_.get("datetime") else None
        
        # Эта проверка все еще полезна как дополнительная гарантия.
        tf = entry.get("timeframe")
        tf_value = tf.value if isinstance(tf, Timeframes) else tf

        trades_list.append({
            "entry_datetime": entry.get("datetime"), "entry_price": entry_price,
            "exit_datetime": exit_.get("datetime"), "exit_price": exit_price,
            "size": size, "pnl": pnl, "pnl_comm": pnl - commission,
            "entry_reason": entry.get("reason"), "exit_reason": exit_.get("reason"),
            "strategy_id": entry.get("strategy_id"), "symbol": entry.get("symbol"),
            "timeframe": tf_value,
            "duration_sec": duration_sec
        })
    return pd.DataFrame(trades_list)

def main():
    """
    Основная функция для оркестрации процесса бэктестинга.
    """
    symbols_to_load = param_ranges["symbol"]
    timeframes_to_load = param_ranges["timeframe"]
    console.print("[cyan]Загрузка всех рыночных данных...[/cyan]")
    market_data = load_market_data(symbols_to_load, timeframes_to_load, start_date=START_DATE, end_date=END_DATE)
    
    param_grid = generate_param_grid(param_ranges)
    tasks = [(params, market_data) for params in param_grid]

    console.print(f"[cyan]Запуск {len(tasks)} бэктестов с использованием до {cpu_count()} ядер CPU...[/cyan]")

    with Pool(processes=cpu_count()) as pool:
        results = list(track(pool.imap_unordered(run_single_backtest, tasks), total=len(tasks), description="[cyan]▶️ Выполнение бэктестов[/cyan]"))
    
    success_count = sum(1 for r in results if r[2] == "Success")
    error_count = sum(1 for r in results if r[2] == "Error")
    nodata_count = sum(1 for r in results if r[2] == "No Data")
    
    console.print("\n" + "="*50)
    console.print(f"[bold green]✅ Все запуски завершены.[/bold green]")
    console.print(f"  - [green]Успешные запуски:[/] {success_count}")
    console.print(f"  - [red]Неудачные запуски:[/] {error_count}")
    console.print(f"  - [yellow]Пропущено (нет данных):[/] {nodata_count}")
    console.print("="*50 + "\n")

if __name__ == "__main__":
    main()

