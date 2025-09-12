#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAMA-SPEED breadth: % монет с быстрой / медленной адаптацией (SC).
Отдельный скрипт – ничего не трогает из предыдущих расчётов.
"""
import os
import json
import pandas as pd
import numpy as np
from tqdm import tqdm
from datetime import datetime, timedelta
import argparse
import matplotlib.pyplot as plt

# ---------- настройки ----------
KAMA_CONFIG      = dict(period=10, fast=2, slow=30)
DEFAULT_TOP_N    = 30
DEFAULT_DAYS     = 730
DATA_FOLDER      = "kline_data"
CORR_FILE        = "correlations_multi_tf.json"
OUT_FILE         = "market_breadth_kama_speed.json"

# ---------- KAMA + SC ----------
def kama_sc(series: pd.Series, period: int, fast: int, slow: int):
    """возвращает (kama_line, sc_series) – smoothing constant 0…1"""
    if len(series) < period:
        return pd.Series(dtype=float, index=series.index), pd.Series(dtype=float, index=series.index)

    direction  = series.diff(period).abs()
    volatility = series.diff().abs().rolling(period).sum()
    er         = (direction / volatility).fillna(0)

    fast_sc = 2 / (fast + 1)
    slow_sc = 2 / (slow + 1)
    sc      = (er * (fast_sc - slow_sc) + slow_sc) ** 2   # 0…1

    # строим KAMA
    kama = pd.Series(index=series.index, dtype=float)
    kama.iloc[period - 1] = series.iloc[period - 1]
    for i in range(period, len(series)):
        kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (series.iloc[i] - kama.iloc[i - 1])
    return kama, sc

# ---------- core ----------
def speed_breadth(top_n: int, history_days: int, corr_file: str, out_file: str, do_plot: bool):
    # 1. корреляции
    try:
        with open(corr_file, encoding='utf-8') as f:
            corr = json.load(f)
    except Exception as e:
        exit(f"Ошибка загрузки {corr_file}: {e}")

    tfs = corr.get("meta", {}).get("timeframes", [])
    start = pd.Timestamp.now().normalize() - timedelta(days=history_days)

    result = {"meta": {
        "indicator": "KAMA-speed-breadth",
        "kama_config": KAMA_CONFIG,
        "history_days": history_days,
        "top_n": top_n,
        "source": corr_file,
        "computed_at": datetime.now().isoformat()
    }, "data": {}}

    for tf in tfs:
        folder = os.path.join(DATA_FOLDER, tf)
        if not os.path.isdir(folder):
            continue

        tf_corr = corr.get(tf, {})
        symbols = sorted(tf_corr, key=lambda x: tf_corr[x]["correlation"], reverse=True)[:top_n]

        fast_series, slow_series = [], []

        for sym in tqdm(symbols, desc=f"SC-speed {tf}", ncols=80,
                        bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}"):
            file = os.path.join(folder, f"{sym}.csv")
            if not os.path.exists(file):
                continue
            try:
                df = pd.read_csv(file, usecols=['datetime', 'close'],
                                 parse_dates=['datetime'], index_col='datetime')
                df = df[~df.index.duplicated(keep='first')]
                df = df.loc[df.index >= start]
                if len(df) < KAMA_CONFIG['period']:
                    continue

                _, sc = kama_sc(df['close'], **KAMA_CONFIG)
                # быстрая адаптация – SC выше медианы
                median_sc = sc.median()
                fast = (sc > median_sc).astype(int).rename(sym)
                slow = (sc <= median_sc).astype(int).rename(sym)   # медленная / замедление
                fast_series.append(fast)
                slow_series.append(slow)
            except Exception:
                continue

        if not fast_series:
            continue

        fast_df = pd.concat(fast_series, axis=1)
        slow_df = pd.concat(slow_series, axis=1)
        valid   = fast_df.notna().sum(axis=1)
        pct_fast = (fast_df.sum(axis=1) / valid * 100).where(valid > 0, 0).dropna()
        pct_slow = (slow_df.sum(axis=1) / valid * 100).where(valid > 0, 0).dropna()

        result["data"][tf] = [
            {"date": idx.isoformat(),
             "pct_speed_fast": round(v[0], 2),
             "pct_speed_slow": round(v[1], 2)}
            for idx, v in zip(pct_fast.index, zip(pct_fast, pct_slow))
        ]

    # 5. save
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"✅  готово: {out_file}")

    # 6. plot (опционально)
    if do_plot:
        plot_speed(result, out_file)

# ---------- plot ----------
def plot_speed(data: dict, out_file: str):
    import matplotlib.dates as mdates
    plt.style.use('ggplot')
    fig, axes = plt.subplots(len(data["data"]), 1, figsize=(12, 2 * len(data["data"])),
                             sharex=True, squeeze=False)
    axes = axes.flatten()

    for ax, tf in zip(axes, data["data"]):
        df = pd.DataFrame(data["data"][tf])
        if df.empty:
            continue
        df["date"] = pd.to_datetime(df["date"])
        ax.plot(df["date"], df["pct_speed_fast"], label='ускорение (fast SC)', color='green', linewidth=1.2)
        ax.plot(df["date"], df["pct_speed_slow"], label='замедление (slow SC)', color='red', linewidth=1.2)
        ax.set_ylabel('% монет')
        ax.set_title(f'{tf}  –  KAMA-speed breadth')
        ax.legend()
        ax.grid(True, ls='--', alpha=0.4)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    plt.tight_layout()
    png = out_file.replace('.json', '.png')
    plt.savefig(png, dpi=150)
    print(f"📊  график: {png}")
    plt.show()

# ---------- CLI ----------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KAMA-speed breadth (730 дней)")
    ap.add_argument('--top-n', type=int, default=DEFAULT_TOP_N, help='монет на ТФ')
    ap.add_argument('--history-days', type=int, default=DEFAULT_DAYS, help='глубина (дней)')
    ap.add_argument('--corr-file', default=CORR_FILE)
    ap.add_argument('--out-file', default=OUT_FILE)
    ap.add_argument('--plot', action='store_true', help='сохранить график')
    args = ap.parse_args()

    speed_breadth(top_n=args.top_n,
                  history_days=args.history_days,
                  corr_file=args.corr_file,
                  out_file=args.out_file,
                  do_plot=args.plot)