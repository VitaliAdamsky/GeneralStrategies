import backtrader as bt

class SuperStrategy(bt.Strategy):
    params = (
        ("rsi_period", 14),
        ("atr_period", 14),
        ("take_profit", None),
        ("strategy_id", ""),
        ("symbol", ""),
        ("timeframe", ""),
        ("indicators", ["RSI", "ATR"])  # ✅ Добавлено поле с названиями индикаторов
    )

    def __init__(self):
        self.rsi = bt.indicators.RSI(self.data.close, period=self.params.rsi_period)
        self.atr = bt.indicators.ATR(self.data, period=self.params.atr_period)
        self.entry_log = []
        self.exit_log = []
        self.equity_curve = []

    def next(self):
        self.equity_curve.append((self.data.datetime.datetime(0), self.broker.getvalue()))

        if not self.position:
            if self.rsi < 30:
                self.buy()
                self.entry_log.append({
                    "timestamp": self.data.datetime.datetime(0),
                    "price": self.data.close[0],
                    "rsi": self.rsi[0],
                    "atr": self.atr[0],
                    "reason": "rsi < 30",
                    "strategy_id": self.params.strategy_id,
                    "symbol": self.params.symbol,
                    "timeframe": self.params.timeframe
                })
        else:
            if self.rsi > 70:
                self.sell()
                self.exit_log.append({
                    "timestamp": self.data.datetime.datetime(0),
                    "price": self.data.close[0],
                    "rsi": self.rsi[0],
                    "atr": self.atr[0],
                    "reason": "rsi > 70",
                    "strategy_id": self.params.strategy_id,
                    "symbol": self.params.symbol,
                    "timeframe": self.params.timeframe
                })
