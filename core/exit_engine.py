import pandas as pd

def evaluate_exit_levels(levels, context):
    """
    levels: список exit-уровней из take_profit["levels"]
    context: {
        "entry_price": float,
        "position_size": float,
        "current_price": float,
        "atr": float,
        "ema": float,
        "kama": float,
        "highest_close": float,
        "lowest_close": float,
        "prev_ema": float,
        "prev_kama": float,
        ...
    }

    Возвращает список уровней, готовых к выходу:
    [
        {"percent": 0.5, "exit_type": "atr", "reason": "..."},
        ...
    ]
    """
    exits = []

    for level in levels:
        exit_type = level["exit_type"]
        params = level.get("params", {})
        percent = level.get("percent", 1.0)

        if exit_type == "atr":
            mult = params.get("mult", 1.0)
            target_price = context["entry_price"] + mult * context["atr"]
            if context["current_price"] >= target_price:
                exits.append({
                    "percent": percent,
                    "exit_type": "atr",
                    "reason": f"Price >= entry + {mult} ATR"
                })

        elif exit_type == "chandelier":
            atr_mult = params.get("atr_mult", 3.0)
            trail_stop = context["highest_close"] - atr_mult * context["atr"]
            if context["current_price"] <= trail_stop:
                exits.append({
                    "percent": percent,
                    "exit_type": "chandelier",
                    "reason": f"Price <= Chandelier stop ({trail_stop:.2f})"
                })

        elif exit_type == "ema_cross":
            if context["prev_ema"] > context["current_price"] and context["ema"] < context["current_price"]:
                exits.append({
                    "percent": percent,
                    "exit_type": "ema_cross",
                    "reason": "Price crossed above EMA"
                })

        elif exit_type == "kama_cross":
            if context["prev_kama"] > context["current_price"] and context["kama"] < context["current_price"]:
                exits.append({
                    "percent": percent,
                    "exit_type": "kama_cross",
                    "reason": "Price crossed above KAMA"
                })

        # можно добавить другие exit_type: "time", "custom", "volatility", etc.

    return exits
