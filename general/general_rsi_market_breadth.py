import os
import json
import pandas as pd
from tqdm import tqdm
from datetime import datetime, timedelta, timezone
import argparse

# --- CONFIGURATION ---
# Optimal RSI periods based on analysis
OPTIMAL_RSI_PERIODS = {
    "4h": 14,
    "8h": 14,
    "12h": 16,
    "1d": 21
}

def calculate_rsi(series: pd.Series, period: int, use_ema: bool = False) -> pd.Series:
    """
    Calculates RSI for a time series.
    Supports both classic (SMA) and alternative (EMA) methods.
    """
    if series.empty or len(series) < period:
        return pd.Series(dtype='float64')
        
    delta = series.diff()
    
    if use_ema:
        # EMA-based RSI, more sensitive to recent prices
        gain = (delta.where(delta > 0, 0)).ewm(span=period, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
    else:
        # Classic SMA-based RSI
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def analyze_market_breadth(top_n, years, corr_file, output_file, data_folder, use_ema, compress_json):
    """
    Main function to calculate and save the market breadth indicator,
    using a unique list of top-N coins for each timeframe.
    """
    # 1. Load the correlations file with data for different timeframes
    try:
        with open(corr_file, 'r', encoding='utf-8') as f:
            correlation_data = json.load(f)
        print(f"Successfully loaded data from '{corr_file}'.")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: Could not read or process '{corr_file}'. {e}")
        return

    meta_corr = correlation_data.get("meta", {})
    timeframes_from_corr = meta_corr.get("timeframes", [])
    
    start_date_filter = datetime.now(timezone.utc) - timedelta(days=365.25 * years)
    breadth_results = {}

    # 2. Iterate through each timeframe defined in the correlations file
    for timeframe in timeframes_from_corr:
        rsi_period = OPTIMAL_RSI_PERIODS.get(timeframe)
        if not rsi_period:
            print(f"Warning: Optimal RSI period for timeframe '{timeframe}' not found. Skipping.")
            continue

        print(f"\n--- Calculating for timeframe: {timeframe} (RSI Period: {rsi_period}, Method: {'EMA' if use_ema else 'SMA'}) ---")
        
        # 3. Get the list of top-N coins FOR THIS TIMEFRAME
        tf_corr_data = correlation_data.get(timeframe, {})
        if not tf_corr_data:
            print(f"No correlation data for {timeframe}. Skipping.")
            continue
        
        sorted_symbols = sorted(tf_corr_data.keys(), key=lambda s: tf_corr_data[s]['correlation'], reverse=True)
        top_symbols_for_tf = sorted_symbols[:top_n]
        print(f"Selected top {len(top_symbols_for_tf)} coins for analysis on {timeframe}.")

        data_path = os.path.join(data_folder, timeframe)
        if not os.path.isdir(data_path):
            print(f"Warning: Directory '{data_path}' not found. Skipping timeframe.")
            continue

        all_rsi_series = []
        
        # 4. Calculate RSI for each coin in the list
        for symbol in tqdm(top_symbols_for_tf, desc=f"Processing coins ({timeframe})"):
            filepath = os.path.join(data_path, f"{symbol}.csv")
            if not os.path.exists(filepath):
                continue

            try:
                df = pd.read_csv(filepath, usecols=['datetime', 'close'], parse_dates=['datetime'], index_col='datetime')
                
                # FIX: Localize the naive datetime index to UTC to make it offset-aware for comparison
                if df.index.tz is None:
                    df.index = df.index.tz_localize('UTC')

                if df.index.min() > start_date_filter:
                    continue
                rsi_series = calculate_rsi(df['close'], rsi_period, use_ema)
                all_rsi_series.append(rsi_series.rename(symbol))
            except Exception as e:
                tqdm.write(f"Error processing '{symbol}' on {timeframe}: {e}")

        if not all_rsi_series:
            print(f"No valid data found for timeframe {timeframe}.")
            continue
            
        # 5. Aggregate the data
        rsi_df = pd.concat(all_rsi_series, axis=1)
        rsi_df = rsi_df[rsi_df.index >= start_date_filter]

        valid_coins = rsi_df.notna().sum(axis=1)
        dist = {
            "0-30": ((rsi_df > 0) & (rsi_df <= 30)).sum(axis=1),
            "30-50": ((rsi_df > 30) & (rsi_df <= 50)).sum(axis=1),
            "50-70": ((rsi_df > 50) & (rsi_df <= 70)).sum(axis=1),
            "70-100": ((rsi_df > 70) & (rsi_df <= 100)).sum(axis=1),
        }
        dist_df = pd.DataFrame(dist)

        market_breadth_df = (dist_df.div(valid_coins, axis=0) * 100).where(valid_coins > 0, 0)
        market_breadth_df['avg_rsi'] = rsi_df.mean(axis=1)
        market_breadth_df = market_breadth_df.dropna()
        
        breadth_results[timeframe] = [
            {
                "date": index.isoformat(),
                "distribution": {
                    "0-30": round(row["0-30"], 2), "30-50": round(row["30-50"], 2),
                    "50-70": round(row["50-70"], 2), "70-100": round(row["70-100"], 2),
                },
                "avg_rsi": round(row["avg_rsi"], 2)
            }
            for index, row in market_breadth_df.iterrows()
        ]
        
        print(f"Calculation for {timeframe} complete. Collected {len(breadth_results[timeframe])} data points.")

    # 6. Write the final JSON
    final_output = {
        "meta": {
            "source_correlation_file": corr_file,
            "top_n_coins_per_tf": top_n,
            "optimal_rsi_periods": OPTIMAL_RSI_PERIODS,
            "rsi_method": "EMA" if use_ema else "SMA",
            "rsi_ranges": ["0-30", "30-50", "50-70", "70-100"],
            "history_years": years,
            "computed_at": datetime.now(timezone.utc).isoformat()
        },
        "data": breadth_results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json_kwargs = {'ensure_ascii': False}
        if compress_json:
            json_kwargs.update({'indent': None, 'separators': (',', ':')})
            print_msg = f"Results saved in compressed format to '{output_file}'."
        else:
            json_kwargs['indent'] = 4
            print_msg = f"Results saved to '{output_file}'."
        json.dump(final_output, f, **json_kwargs)
        
    print(f"\nMarket breadth analysis complete. {print_msg}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Market breadth analyzer based on RSI using coin lists for each timeframe.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('--top-n', type=int, default=30, help='Number of top coins from the correlation list for each TF.')
    parser.add_argument('--years', type=float, default=2.0, help='Depth of history in years (float is allowed, e.g., 1.5).')
    parser.add_argument('--corr-file', type=str, default="correlations_multi_tf.json", help='File with correlation data for each TF.')
    parser.add_argument('--output-file', type=str, default="market_breadth_rsi.json", help='Output file for results.')
    parser.add_argument('--data-folder', type=str, default="kline_data", help='Folder with historical data.')
    parser.add_argument('--use_ema', action='store_true', help='Use EMA instead of SMA for RSI calculation.')
    parser.add_argument('--compress_json', action='store_true', help='Compress the output JSON file to save space.')
    
    args = parser.parse_args()
    
    analyze_market_breadth(
        top_n=args.top_n, 
        years=args.years, 
        corr_file=args.corr_file, 
        output_file=args.output_file, 
        data_folder=args.data_folder,
        use_ema=args.use_ema,
        compress_json=args.compress_json
    )

