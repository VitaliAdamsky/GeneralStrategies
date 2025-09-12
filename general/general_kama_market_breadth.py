#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KAMA-market-breadth (фиксировано 730 дней).
Полностью готовый скрипт – запускай и забудь.
"""
import os
import json
import pandas as pd
from tqdm import tqdm
from datetime import datetime, timedelta
import argparse

# ---------- конфиг ----------
KAMA_CONFIG    = dict(period=10, fast=2, slow=30)
HISTORY_DAYS   = 730          # ← ГЛУБИНА (дни)
DEFAULT_TOP_N  = 30
DATA_FOLDER    = "kline_data"
BASE_COIN      = "BTCUSDT"
CORR_FILE      = "correlations_multi_tf.json"
OUT_FILE       = "market_breadth_kama.json"

# ---------- KAMA ----------
def kama(series: pd.Series, period: int, fast: int, slow: int) -> pd.Series:
    if len(series) < period:
        return pd.Series(dtype=float, index=series.index)
    direction  = series.diff(period).abs()
    volatility = series.diff().abs().rolling(period).sum()
    er         = (direction / volatility).fillna(0)
    fast_sc    = 2 / (fast + 1)
    slow_sc    = 2 / (slow + 1)
    sc         = (er * (fast_sc - slow_sc) + slow_sc) ** 2

    kama = pd.Series(index=series.index, dtype=float)
    kama.iloc[period - 1] = series.iloc[period - 1]
    for i in range(period, len(series)):
        kama.iloc[i] = kama.iloc[i - 1] + sc.iloc[i] * (series.iloc[i] - kama.iloc[i - 1])
    return kama

# ---------- core ----------
def analyze(top_n: int, history_days: int, corr_file: str, out_file: str):
    # 1. читаем корреляции
    try:
        with open(corr_file, encoding='utf-8') as f:
            corr = json.load(f)
    except Exception as e:
        exit(f"Не удалось загрузить {corr_file}: {e}")

    tfs = corr.get("meta", {}).get("timeframes", [])
    start = pd.Timestamp.now().normalize() - timedelta(days=history_days)

    result = {"meta": {
        "indicator": "KAMA-breadth",
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

        above_series = []
        for sym in tqdm(symbols, desc=f"KAMA {tf}", ncols=80,
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

                kline = kama(df['close'], **KAMA_CONFIG)
                above = (df['close'] > kline).astype(int).rename(sym)
                above_series.append(above)
            except Exception:
                continue

        if not above_series:
            continue

        breadth = pd.concat(above_series, axis=1)
        valid   = breadth.notna().sum(axis=1)
        pct     = (breadth.sum(axis=1) / valid * 100).where(valid > 0, 0).dropna()

        result["data"][tf] = [
            {"date": idx.isoformat(), "pct_above_kama": round(v, 2)}
            for idx, v in pct.items()
        ]

    # 4. save
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"✅  готово: {out_file}")

# ---------- CLI ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="KAMA-breadth (фикс. 730 дней)")
    parser.add_argument('--top-n', type=int, default=DEFAULT_TOP_N, help='монет на ТФ')
    parser.add_argument('--out-file', default=OUT_FILE, help='выходной JSON')
    args = parser.parse_args()

    analyze(top_n=args.top_n,
            history_days=HISTORY_DAYS,
            corr_file=CORR_FILE,
            out_file=args.out_file)