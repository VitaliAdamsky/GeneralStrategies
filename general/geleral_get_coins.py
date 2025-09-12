import os
import re
import time
import json
import math
import ccxt
import requests
import numpy as np
from tqdm import tqdm

# --- НАСТРОЙКИ ---
MIN_VOLUME = 3_000_000
SAVE_FILE = 'coins.json'
LOCAL_LOGO_DIR = 'logo'             # Папка с вашими локальными лого
MISSING_LOGO_DIR = 'missing_logo'   # Папка для скачанных недостающих лого

# --- Создаем директории, если их нет ---
os.makedirs(LOCAL_LOGO_DIR, exist_ok=True)
os.makedirs(MISSING_LOGO_DIR, exist_ok=True)


# --- ФУНКЦИИ ИЗ ПРЕДЫДУЩИХ ВЕРСИЙ (с небольшими адаптациями) ---

def normalize_symbol(symbol: str) -> str:
    """
    Приводит биржевой тикер к базовому имени актива для поиска логотипа.
    '1000PEPEUSDT' -> 'pepe'
    '1INCHUSDT'    -> '1inch'
    'BTCUSDT'      -> 'btc'
    """
    # Сначала убираем биржевые суффиксы
    base = symbol.split(":")[0].replace("/", "")
    # Убираем USDT
    base = base.upper().replace('USDT', '')
    
    # Особый случай для 1INCH
    if base == '1INCH':
        return '1inch'
    
    # Убираем все ведущие цифры и приводим к нижнему регистру
    return re.sub(r'^\d+', '', base).lower()

def fetch_usdt_futures(exchange_name, label=''):
    """Загружает данные о фьючерсах с указанной биржи."""
    exchange = None
    try:
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class({"options": {"defaultType": "future"}})
        markets = exchange.load_markets()
        symbols = [s for s, m in markets.items() if m.get("linear") and m.get("quote") == "USDT" and m.get("active")]
        result = {}
        pbar = tqdm(symbols, desc=f"Загрузка {label}", ncols=100)
        for symbol in pbar:
            try:
                ticker = exchange.fetch_ticker(symbol)
                vol = ticker.get("quoteVolume", 0)
                if vol and vol > 0: result[symbol] = vol
            except Exception:
                pass
            time.sleep(exchange.rateLimit / 1000)
        return result
    finally:
        if exchange and hasattr(exchange, 'close'):
            try:
                exchange.close()
            except Exception:
                pass

def assign_categories_by_volume(coins):
    """Присваивает категории на основе квантилей объема торгов."""
    if not coins:
        return
    coins.sort(key=lambda x: x['volume'], reverse=True)
    volumes = np.array([c['volume'] for c in coins])
    quantiles = np.quantile(volumes, [0, 1/6, 2/6, 3/6, 4/6, 5/6, 1])
    quantiles[0] -= 1
    def get_cat(v):
        if v >= quantiles[5]: return "I"
        if v >= quantiles[4]: return "II"
        if v >= quantiles[3]: return "III"
        if v >= quantiles[2]: return "IV"
        if v >= quantiles[1]: return "V"
        return "VI"
    for coin in coins:
        coin['category'] = get_cat(coin['volume'])


# --- НОВЫЕ И ОБЪЕДИНЕННЫЕ ФУНКЦИИ ---

def find_local_logo_path(base_name, directory, extensions=['.svg', '.png', '.jpg', '.jpeg']):
    """Ищет файл по базовому имени с разными расширениями."""
    for ext in extensions:
        path = os.path.join(directory, base_name + ext)
        if os.path.exists(path):
            return os.path.basename(path)
    return None

def download_missing_logos(symbols_to_download):
    """
    Скачивает логотипы для списка недостающих символов и возвращает карту 'символ -> имя файла'.
    """
    if not symbols_to_download:
        return {}
        
    print(f"\nНачинаю загрузку {len(symbols_to_download)} недостающих логотипов с CoinGecko...")
    downloaded_map = {}

    # 1. Получаем карту 'символ -> id' с CoinGecko
    print("Получение ID монет с CoinGecko...")
    try:
        url = "https://api.coingecko.com/api/v3/coins/list"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        id_map = {coin['symbol'].lower(): coin['id'] for coin in response.json()}
    except requests.exceptions.RequestException as e:
        print(f"Критическая ошибка: не удалось получить список монет CoinGecko. {e}")
        return downloaded_map

    # 2. Находим ID для наших недостающих символов
    target_ids = {id_map.get(s): s for s in symbols_to_download if id_map.get(s)}
    if not target_ids:
        print("Не удалось найти ID ни для одного из недостающих символов.")
        return downloaded_map

    # 3. Пакетный запрос и скачивание
    chunk_size = 150
    id_list = list(target_ids.keys())
    
    for i in tqdm(range(0, len(id_list), chunk_size), desc="Скачивание пакетов", ncols=100):
        chunk_ids = id_list[i:i + chunk_size]
        ids_string = ",".join(chunk_ids)
        markets_url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids_string}"
        
        try:
            markets_response = requests.get(markets_url, timeout=15)
            markets_response.raise_for_status()
            coins_data = markets_response.json()

            for coin_data in coins_data:
                symbol_lower = coin_data.get('symbol').lower()
                image_url = coin_data.get('image')
                if not image_url: continue

                file_extension = os.path.splitext(image_url.split('?')[0])[1] or '.png'
                file_name = f"{symbol_lower}{file_extension}"
                file_path = os.path.join(MISSING_LOGO_DIR, file_name)
                
                try:
                    img_data = requests.get(image_url, timeout=10).content
                    with open(file_path, 'wb') as f:
                        f.write(img_data)
                    # Сохраняем имя скачанного файла для обновления JSON
                    downloaded_map[symbol_lower] = file_name
                except requests.exceptions.RequestException as img_e:
                    print(f"Не удалось скачать {image_url}: {img_e}")

            time.sleep(2) # Задержка между пакетами
        except requests.exceptions.RequestException as e:
            print(f"Ошибка при обработке пакета: {e}")
            
    return downloaded_map


def main():
    """Основная функция выполнения скрипта."""
    print("--- Шаг 1: Загрузка данных с бирж ---")
    binance_data = fetch_usdt_futures('binance', label='Binance')
    bybit_data = fetch_usdt_futures('bybit', label='Bybit')

    # Объединение данных
    combined = {}
    all_symbols = set(binance_data.keys()) | set(bybit_data.keys())
    
    for sym in all_symbols:
        vol = binance_data.get(sym, 0) + bybit_data.get(sym, 0)
        if vol >= MIN_VOLUME:
            key = sym.split(":")[0].replace("/", "")
            exchanges = []
            if sym in binance_data: exchanges.append('Binance')
            if sym in bybit_data: exchanges.append('Bybit')
            combined[key] = {'volume': vol, 'exchanges': exchanges}

    print(f"\n--- Шаг 2: Поиск локальных логотипов в '{LOCAL_LOGO_DIR}' ---")
    all_coins = []
    missing_logo_symbols = set()
    
    for sym, data in combined.items():
        base_asset = normalize_symbol(sym)
        logo_file = find_local_logo_path(base_asset, LOCAL_LOGO_DIR)
        
        if not logo_file:
            missing_logo_symbols.add(base_asset)

        all_coins.append({
            'symbol': sym,
            'base_asset': base_asset, # Временное поле
            'volume': data['volume'],
            'exchanges': data['exchanges'],
            'logoUrl': logo_file or ""
        })

    print(f"Найдено локальных логотипов: {len(all_coins) - len(missing_logo_symbols)}")
    print(f"Не найдено локальных логотипов для {len(missing_logo_symbols)} монет.")

    # --- Шаг 3: Скачивание недостающих логотипов ---
    if missing_logo_symbols:
        downloaded_files = download_missing_logos(list(missing_logo_symbols))
        
        # Обновляем logoUrl для скачанных файлов
        print("\nОбновление 'logoUrl' для скачанных файлов...")
        for coin in all_coins:
            if not coin['logoUrl']: # Если лого не был найден локально
                base_asset = coin['base_asset']
                if base_asset in downloaded_files:
                    # Путь будет указывать на папку с недостающими лого
                    coin['logoUrl'] = os.path.join(MISSING_LOGO_DIR, downloaded_files[base_asset])
    
    # --- Шаг 4: Финальная обработка и сохранение ---
    print("\n--- Шаг 4: Присвоение категорий и сохранение ---")
    assign_categories_by_volume(all_coins)

    for coin in all_coins:
        coin.pop('base_asset', None) # Удаляем временный ключ

    all_coins.sort(key=lambda x: x['volume'], reverse=True)

    result = {
        'binance': [c for c in all_coins if 'Binance' in c['exchanges']],
        'bybit': [c for c in all_coins if 'Bybit' in c['exchanges']]
    }
    
    with open(SAVE_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Готово! Результаты сохранены в {SAVE_FILE}")
    print(f"Скачанные логотипы находятся в папке '{MISSING_LOGO_DIR}'.")


if __name__ == "__main__":
    main()
