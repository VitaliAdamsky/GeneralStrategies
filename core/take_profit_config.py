from enum import Enum

class TakeProfitMode(str, Enum):
    FULL = "full"       # Выход всей позиции по одному условию
    PARTIAL = "partial" # Выход частями по уровням

class ExitType(str, Enum):
    ATR = "atr"               # Цена >= entry + mult × ATR
    CHANDELIER = "chandelier" # Цена >= high - atr_mult × ATR
    EMA_CROSS = "ema_cross"   # EMA пересекает цену
    KAMA_CROSS = "kama_cross" # KAMA пересекает цену
    CUSTOM = "custom"         # Любая пользовательская логика
