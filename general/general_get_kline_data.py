import os
import json
import asyncio
import ccxt.async_support as ccxt
import pandas as pd
from datetime import datetime
import aiofiles
from tqdm.asyncio import tqdm
from io import StringIO

# --- НАСТРОЙКИ ---
START_DATE = "2020-01-01T00:00:00Z"
END_DATE = "2025-09-20T00:00:00Z"
TIMEFRAMES = ["15m", "30m", "1h", "4h", "8h", "12h", "1d", "1w"]
DATA_FOLDER = "kline_data"
MAX_CONCURRENT_REQUESTS = 10
MAX_RETRIES = 3
RETRY_DELAY = 10

def iso_to_ms(iso_str):
    """Конвертирует строку ISO 8601 в миллисекунды."""
    dt = datetime.strptime(iso_str, "%Y-%m-%dT%H:%M:%SZ")
    return int(dt.timestamp() * 1000)

async def get_last_timestamp(filename):
    """
    Эффективно считывает CSV и возвращает последнюю метку времени в мс.
    Не загружает весь файл в память.
    """
    if not os.path.isfile(filename) or os.path.getsize(filename) == 0:
        return None
    try:
        async with aiofiles.open(filename, mode='r', encoding='utf-8') as f:
            content = await f.read()
        df = pd.read_csv(StringIO(content), usecols=['datetime'])
        if not df.empty:
            last_dt = pd.to_datetime(df['datetime'].iloc[-1])
            # print(f"Файл {os.path.basename(filename)} найден. Последняя запись: {last_dt}.") # Убрано для чистоты лога
            return int(last_dt.timestamp() * 1000)
    except Exception as e:
        print(f"Предупреждение: не удалось прочитать последнюю метку из {filename}: {e}. Файл может быть поврежден.")
    return None

async def fetch_ohlcv_paginated(exchange, symbol, timeframe, since, end_ts, limit=1000, max_retries=3):
    """
    Загружает OHLCV данные с пагинацией и обработкой ошибок.
    Возвращает None, если символ не найден или превышено число попыток.
    """
    all_ohlcv = []
    current_since = since

    while current_since < end_ts:
        retries = 0
        ohlcv = None
        while retries < max_retries:
            try:
                ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=current_since, limit=limit)
                break
            except ccxt.BadSymbol as e:
                print(f"Ошибка: {e}. Символ {symbol} не найден на {exchange.id}. Пропускаем.")
                return None
            except (ccxt.NetworkError, ccxt.ExchangeNotAvailable, ccxt.RequestTimeout) as e:
                retries += 1
                print(f"Сетевая ошибка при загрузке {symbol} {timeframe}: {e}. Попытка {retries}/{max_retries}...")
                if retries < max_retries:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"Не удалось загрузить {symbol} после {max_retries} попыток. Пропускаем.")
                    return None
            except ccxt.ExchangeError as e:
                retries += 1
                print(f"Ошибка биржи при загрузке {symbol} {timeframe}: {e}. Попытка {retries}/{max_retries}...")
                if retries < max_retries:
                    await asyncio.sleep(RETRY_DELAY)
                else:
                    print(f"Не удалось загрузить {symbol} после {max_retries} попыток. Пропускаем.")
                    return None

        if ohlcv is None: break
        if not ohlcv: break

        all_ohlcv.extend(ohlcv)
        current_since = ohlcv[-1][0] + 1
        
        # Более надежная пауза для соблюдения rate limits, с минимумом в 0.5с
        sleep_duration = max(exchange.rateLimit or 1000, 500) / 1000
        await asyncio.sleep(sleep_duration)

    return [candle for candle in all_ohlcv if candle[0] <= end_ts]

async def fetch_and_save_task(semaphore, exchange, symbol_to_save, symbol_to_fetch, timeframe, folder, start_ms, end_ms, failed_tasks, pbar):
    """Задача-обертка для безопасного выполнения, логирования ошибок и обновления прогресс-бара."""
    try:
        success = await fetch_and_save(semaphore, exchange, symbol_to_save, symbol_to_fetch, timeframe, folder, start_ms, end_ms)
        if not success:
            failed_tasks.append((symbol_to_save, timeframe))
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА в задаче для {symbol_to_save} {timeframe}: {e}")
        failed_tasks.append((symbol_to_save, timeframe))
    finally:
        pbar.update(1)
        pbar.set_postfix_str(f"Обработан: {symbol_to_save}")

async def fetch_and_save(semaphore, exchange, symbol_to_save, symbol_to_fetch, timeframe, folder, start_ms, end_ms):
    """Логика загрузки и ДОЗАПИСИ данных для одного символа."""
    filename = os.path.join(folder, symbol_to_save.replace("/", "_") + ".csv")
    
    last_ts = await get_last_timestamp(filename)
    fetch_start = start_ms if last_ts is None else last_ts + 1

    if fetch_start >= end_ms:
        # Данные уже актуальны, молча выходим.
        return True

    async with semaphore:
        # Убрано для чистоты лога, pbar показывает текущий символ.
        # if last_ts is None:
        #     print(f"Начинаем загрузку {symbol_to_save} ({timeframe}) с {START_DATE}...")
        # else:
        #     print(f"Докачиваем {symbol_to_save} ({timeframe}) с {datetime.fromtimestamp(fetch_start / 1000)}...")
            
        ohlcv = await fetch_ohlcv_paginated(exchange, symbol_to_fetch, timeframe, fetch_start, end_ms, max_retries=MAX_RETRIES)

        if ohlcv is None:
            print(f"Не удалось получить данные для {symbol_to_save} ({timeframe}). Задача помечена как неуспешная.")
            return False

        if not ohlcv:
            # print(f"Нет новых данных для {symbol_to_save} ({timeframe}).") # Убрано для чистоты лога
            return True

        df_new = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
        
        if last_ts is not None:
            df_new = df_new[df_new['timestamp'] > last_ts]

        if df_new.empty:
            # print(f"Нет УНИКАЛЬНЫХ новых данных для {symbol_to_save} ({timeframe}).") # Убрано для чистоты лога
            return True

        df_new["datetime"] = pd.to_datetime(df_new["timestamp"], unit='ms')

        file_exists = last_ts is not None
        mode = 'a' if file_exists else 'w'
        write_header = not file_exists

        async with aiofiles.open(filename, mode=mode, encoding='utf-8') as f:
            await f.write(df_new.to_csv(index=False, header=write_header, columns=["datetime", "open", "high", "low", "close", "volume"]))
        
        # Убрано для чистоты лога
        # status_msg = f"Дописано {len(df_new)} строк" if file_exists else f"Создан файл, записей: {len(df_new)}"
        # print(f"Сохранены данные для {symbol_to_save} ({timeframe}). {status_msg}")
        return True

async def main():
    """Главная функция запуска скрипта."""
    if not os.path.isfile("coins.json"):
        print("Ошибка: файл 'coins.json' не найден.")
        return
        
    with open("coins.json", "r") as f:
        data = json.load(f)

    binance = ccxt.binance({"options": {"defaultType": "future"}})
    bybit = ccxt.bybit({"options": {"defaultType": "future"}})
    
    start_ms = iso_to_ms(START_DATE)
    end_ms = iso_to_ms(END_DATE)
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    all_coins = data.get("binance", []) + data.get("bybit", [])
    unique_coins = {coin["symbol"]: coin for coin in all_coins}
    failed_tasks = []

    for timeframe in TIMEFRAMES:
        folder = os.path.join(DATA_FOLDER, timeframe)
        os.makedirs(folder, exist_ok=True)
        print(f"\n--- Начинаем загрузку для таймфрейма {timeframe} ---")
        
        pbar = tqdm(total=len(unique_coins), desc=f"Загрузка {timeframe}")
        tasks = []
        for symbol, coin_data in unique_coins.items():
            exchanges = coin_data.get("exchanges", [])
            exchange = binance if "Binance" in exchanges else bybit
            
            symbol_to_fetch = symbol if "/" in symbol else f"{symbol[:-4]}/{symbol[-4:]}" if symbol.endswith("USDT") else symbol
                
            tasks.append(fetch_and_save_task(semaphore, exchange, symbol, symbol_to_fetch, timeframe, folder, start_ms, end_ms, failed_tasks, pbar))
        
        await asyncio.gather(*tasks)
        pbar.close()
        print(f"--- Загрузка для таймфрейма {timeframe} завершена ---")
    
    if failed_tasks:
        print(f"\n--- {len(failed_tasks)} задач не удалось выполнить. Повторный запуск... ---")
        tasks_to_retry = list(failed_tasks)
        failed_tasks.clear()

        pbar_retry = tqdm(total=len(tasks_to_retry), desc="Повторная загрузка")
        retry_tasks = []
        for symbol, tf in tasks_to_retry:
            coin_data = unique_coins.get(symbol, {})
            exchange = binance if "Binance" in coin_data.get("exchanges", []) else bybit
            symbol_to_fetch = symbol if "/" in symbol else f"{symbol[:-4]}/{symbol[-4:]}"
            folder = os.path.join(DATA_FOLDER, tf)
            retry_tasks.append(
                fetch_and_save_task(semaphore, exchange, symbol, symbol_to_fetch, tf, folder, start_ms, end_ms, failed_tasks, pbar_retry)
            )
        if retry_tasks:
            await asyncio.gather(*retry_tasks)
        pbar_retry.close()


    await binance.close()
    await bybit.close()
    
    if failed_tasks:
        print("\n--- Некоторые задачи не удалось выполнить после повторной попытки: ---")
        for symbol, tf in failed_tasks:
            print(f"  - Символ: {symbol}, Таймфрейм: {tf}")
        with open("failed_tasks.log", "w") as f:
            for symbol, tf in failed_tasks:
                f.write(f"{symbol},{tf}\n")
        print("Список невыполненных задач сохранен в failed_tasks.log")

    print("\nВсе задачи выполнены.")

if __name__ == "__main__":
    asyncio.run(main())

