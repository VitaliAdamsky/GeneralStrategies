import json
import os
import shutil

# --- НАСТРОЙКИ ---
COINS_FILE = "coins.json"
DATA_FOLDER = "kline_data"
TIMEFRAMES = ["15m", "30m", "1h", "4h", "8h", "12h", "1d", "1w"]

def find_and_clean_bad_data():
    """
    Находит монеты с некачественными данными, показывает отчет,
    запрашивает подтверждение и только после этого удаляет файлы
    и записи из coins.json.
    """
    try:
        with open(COINS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Ошибка: Файл {COINS_FILE} не найден.")
        return
    except json.JSONDecodeError:
        print(f"Ошибка: Не удалось прочитать JSON из файла {COINS_FILE}.")
        return

    problem_coins = {}
    symbols_to_remove = set()
    all_coins = data.get("binance", []) + data.get("bybit", [])

    # --- Шаг 1: Найти все монеты с любым статусом, кроме 'ok' ---
    for coin in all_coins:
        symbol = coin.get("symbol")
        if not symbol:
            continue

        issues = []
        for timeframe in TIMEFRAMES:
            status_key = f"{timeframe}_status"
            status = coin.get(status_key)

            if status is not None and status != "ok":
                issues.append(f"Таймфрейм {timeframe}: статус '{status}'")
        
        if issues:
            problem_coins[symbol] = issues
            symbols_to_remove.add(symbol)

    # --- Шаг 2: Показать промежуточный отчет ---
    if not problem_coins:
        print("Проверка завершена. Монет с некачественными данными не найдено.")
        return

    print("--- Промежуточный отчет: найдены монеты с проблемами ---")
    for symbol, issues_list in problem_coins.items():
        print(f"\nМонета: {symbol}")
        for issue in issues_list:
            print(f"  - {issue}")
    print("\n" + "="*50)

    # --- Шаг 3: Запросить подтверждение на удаление ---
    confirm = input(f"Найдено {len(symbols_to_remove)} монет с проблемами. Удалить эти монеты и все их данные? (yes/no): ")
    
    if confirm.lower() != 'yes':
        print("Операция отменена. Данные не были изменены.")
        return

    # --- Шаг 4: Если подтверждено, выполнить удаление ---
    print("\nПодтверждение получено. Начинаем очистку...")
    
    # Удаление файлов
    print("Удаление файлов из kline_data...")
    files_deleted_count = 0
    for symbol in symbols_to_remove:
        for timeframe in TIMEFRAMES:
            file_path = os.path.join(DATA_FOLDER, timeframe, f"{symbol.replace('/', '_')}.csv")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    files_deleted_count += 1
                    # print(f"  Удален файл: {file_path}") # Можно раскомментировать для детального лога
                except OSError as e:
                    print(f"  Ошибка при удалении файла {file_path}: {e}")
    print(f"Удаление файлов завершено. Всего удалено файлов: {files_deleted_count}")
    print("-" * 30)

    # Удаление монет из coins.json
    print(f"Обновление файла {COINS_FILE}...")
    
    original_binance_count = len(data.get("binance", []))
    data["binance"] = [coin for coin in data.get("binance", []) if coin.get("symbol") not in symbols_to_remove]
    removed_from_binance = original_binance_count - len(data["binance"])

    original_bybit_count = len(data.get("bybit", []))
    data["bybit"] = [coin for coin in data.get("bybit", []) if coin.get("symbol") not in symbols_to_remove]
    removed_from_bybit = original_bybit_count - len(data["bybit"])

    # Сохранение обновленного JSON
    try:
        with open(COINS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Файл {COINS_FILE} успешно обновлен.")
        print(f"Удалено монет из списка Binance: {removed_from_binance}")
        print(f"Удалено монет из списка Bybit: {removed_from_bybit}")
        print("Очистка полностью завершена.")
    except Exception as e:
        print(f"Ошибка при сохранении файла {COINS_FILE}: {e}")


if __name__ == "__main__":
    find_and_clean_bad_data()
