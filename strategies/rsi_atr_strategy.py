import backtrader as bt
from core.take_profit_config import TakeProfitMode
from core import evaluate_exit_levels

class SuperStrategy(bt.Strategy):
    """
    Стратегия, основанная на входе по RSI и выходе по ATR.
    Логика полностью инкапсулирована и не зависит от способа запуска.
    """
    params = dict(
        rsi_period=14,
        atr_period=14,
        take_profit=None
    )

    def __init__(self):
        # --- Индикаторы ---
        self.rsi = bt.indicators.RSI_SMA(self.data.close, period=self.p.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=self.p.atr_period)
        # Дополнительные индикаторы для exit_engine
        self.ema = bt.indicators.EMA(self.data.close, period=20)
        self.kama = bt.indicators.KAMA(self.data.close, period=20)

        # --- Логика выходов ---
        if not self.p.take_profit:
            raise ValueError("Параметр 'take_profit' не был передан в стратегию.")
            
        self.exit_plan = self.p.take_profit["levels"]
        self.exit_mode = TakeProfitMode(self.p.take_profit["mode"])
        
        # --- Внутреннее состояние для логирования ---
        self.exit_log = []
        self.equity_curve = []

    def next(self):
        self.equity_curve.append([self.data.datetime.datetime(0), self.broker.getvalue()])

        if not self.position:
            # --- Логика входа ---
            if self.rsi[0] < 30:
                size_to_buy = (self.broker.get_cash() / self.data.close[0]) * 0.99
                self.buy(size=size_to_buy)
        else:
            # --- Логика выхода ---
            context = {
                "entry_price": self.position.price,
                "position_size": self.position.size,
                "current_price": self.data.close[0],
                "atr": self.atr[0],
                "ema": self.ema[0],
                "kama": self.kama[0],
                "prev_ema": self.ema[-1],
                "prev_kama": self.kama[-1],
                "highest_close": max(self.data.close.get(size=20)),
                "lowest_close": min(self.data.close.get(size=20))
            }

            exit_levels = evaluate_exit_levels(self.exit_plan, context)
            if not exit_levels:
                return

            if self.exit_mode == TakeProfitMode.FULL:
                exit_info = exit_levels[0]
                self.close()
                self.log_exit(exit_info)

            elif self.exit_mode == TakeProfitMode.PARTIAL:
                for exit_info in exit_levels:
                    size_to_close = self.position.size * exit_info["percent"]
                    self.sell(size=size_to_close)
                    self.log_exit(exit_info)

    def log_exit(self, exit_info):
        """Логирует информацию о выходе из позиции."""
        self.exit_log.append({
            "timestamp": str(self.data.datetime.datetime(0)),
            "price": self.data.close[0],
            "percent": exit_info["percent"],
            "exit_type": exit_info["exit_type"],
            "reason": exit_info["reason"]
        })
