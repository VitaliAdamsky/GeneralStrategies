from itertools import product

def generate_param_grid(param_ranges):
    """
    Поддерживает вложенные индикаторы:
    {
        "indicators": [
            {"name": "RSI", "len": [14, 21]},
            {"name": "ATR", "len": [14, 21]}
        ],
        "take_profit": [...]
    }

    Возвращает список конфигураций:
    [
        {"indicators": [{"name": "RSI", "len": 14}, {"name": "ATR", "len": 14}], ...},
        {"indicators": [{"name": "RSI", "len": 14}, {"name": "ATR", "len": 21}], ...},
        ...
    ]
    """
    flat_keys = []
    flat_values = []

    for key, value in param_ranges.items():
        if key == "indicators":
            # Разворачиваем все len внутри каждого индикатора
            indicator_combos = []
            for ind in value:
                name = ind["name"]
                lens = ind["len"] if isinstance(ind["len"], list) else [ind["len"]]
                indicator_combos.append([{"name": name, "len": l} for l in lens])
            # Получаем декартово произведение всех индикаторов
            indicator_grid = [list(combo) for combo in product(*indicator_combos)]
            flat_keys.append("indicators")
            flat_values.append(indicator_grid)
        else:
            flat_keys.append(key)
            flat_values.append(value)

    grid = [dict(zip(flat_keys, combo)) for combo in product(*flat_values)]
    return grid
