#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Мульти-ТФ корреляция с BTC.
История = ровно `days` календарных дней.
В файле сохраняем:
  - correlation
  - matching_bars  ← количество баров (6/3/2/1 в день)
"""
import os
import json
import argparse
import pandas as pd
from tqdm import tqdm
from datetime import datetime, timedelta

DATA_FOLDER      = "kline_data"
BASE_COIN        = "BTCUSDT"
OUTPUT_FILE      = "correlations_multi_tf.json"
TIMEFRAMES       = ["4h", "8h", "12h", "1d"]

DEFAULT_TOP_N    = 30
DEFAULT_DAYS     = 730
MIN_MATCHING_BARS = 50          # минимум баров после merge

# ---------- утилиты ----------
def load_series(path: str, symbol: str):
    try:
        df = pd.read_csv(path, usecols=["datetime", "close"],
                         parse_dates=["datetime"], index_col="datetime")
        df = df[~df.index.duplicated(keep="first")]
        return df["close"].rename(symbol)
    except Exception:
        return None

def corr_for_tf(tf: str, top_n: int, days: int):
    """TOP-N корреляций для одного ТФ (ровно `days` календарных дней)"""
    start_cut = pd.Timestamp.now().normalize() - timedelta(days=days)   # tz-naive
    folder    = os.path.join(DATA_FOLDER, tf)
    if not os.path.isdir(folder):
        return {}

    base = load_series(os.path.join(folder, f"{BASE_COIN}.csv"), BASE_COIN)
    if base is None:
        return {}
    base = base.loc[base.index >= start_cut]
    if len(base) < MIN_MATCHING_BARS:
        return {}

    files = [f for f in os.listdir(folder) if f.endswith(".csv") and f != f"{BASE_COIN}.csv"]
    res   = {}

    for fname in tqdm(files, desc=f"CORR {tf}", ncols=80,
                      bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt}"):
        symbol = fname.replace(".csv", "")
        ser    = load_series(os.path.join(folder, fname), symbol)
        if ser is None:
            continue
        ser = ser.loc[ser.index >= start_cut]
        if len(ser) < MIN_MATCHING_BARS:
            continue

        merged = pd.concat([base, ser], axis=1, join="inner").dropna()
        if len(merged) < MIN_MATCHING_BARS:
            continue

        corr = merged.iloc[:, 0].corr(merged.iloc[:, 1])
        if pd.notna(corr):
            res[symbol] = {"correlation": float(corr),
                           "matching_bars": int(len(merged))}

    top_syms = sorted(res, key=lambda s: res[s]["correlation"], reverse=True)[:top_n]
    return {s: res[s] for s in top_syms}

# ---------- CLI ----------
def main():
    parser = argparse.ArgumentParser(description="Корреляция с BTC по 4-м ТФ (730 дней)")
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_N, help="сколько монет оставить")
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS, help="глубина истории (дней)")
    args = parser.parse_args()

    out = {"meta": {
        "base_coin": BASE_COIN,
        "top_n": args.top,
        "history_days": args.days,
        "timeframes": TIMEFRAMES,
        "computed_at": datetime.now().isoformat()
    }}

    for tf in TIMEFRAMES:
        out[tf] = corr_for_tf(tf, args.top, args.days)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"✅  готово: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()