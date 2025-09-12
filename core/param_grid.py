from itertools import product

def generate_param_grid(param_ranges):
    """
    Принимает словарь параметров с диапазонами:
    {
        "rsi_period": [10, 14],
        "atr_period": [14, 21],
        ...
    }

    Возвращает список конфигураций:
    [
        {"rsi_period": 10, "atr_period": 14, ...},
        {"rsi_period": 10, "atr_period": 21, ...},
        ...
    ]
    """
    keys = list(param_ranges.keys())
    values = list(param_ranges.values())
    grid = [dict(zip(keys, combo)) for combo in product(*values)]
    return grid
