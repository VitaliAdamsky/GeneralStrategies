import backtrader as bt

class SuperStrategy(bt.Strategy):

    params = (
        ("take_profit", None),
        ("strategy_id", ""),
        ("symbol", ""),
        ("timeframe", ""),
        ("indicators", [  # пример: [{"name": "RSI", "len": 14}, {"name": "ATR", "len": 14}]
            {"name": "RSI", "len": 14},
            {"name": "ATR", "len": 14}
        ])
    )

    def __init__(self):
        self.indicator_objects = {}
        self.entry_log = []
        self.exit_log = []
        self.equity_curve = []

        for ind_cfg in self.params.indicators:
            name = ind_cfg.get("name")
            if name == "RSI":
                period = ind_cfg.get("len", 14)
                self.indicator_objects["RSI"] = bt.indicators.RSI(self.data.close, period=period)

            elif name == "ATR":
                period = ind_cfg.get("len", 14)
                self.indicator_objects["ATR"] = bt.indicators.ATR(self.data, period=period)

            else:
                raise ValueError(f"❌ Неизвестный индикатор: {name}")

    def next(self):
        self.equity_curve.append((self.data.datetime.datetime(0), self.broker.getvalue()))

        rsi = self.indicator_objects.get("RSI")
        atr = self.indicator_objects.get("ATR")

        if not self.position:
            if rsi and rsi[0] < 30:
                self.buy()
                self.entry_log.append({
                    "timestamp": self.data.datetime.datetime(0),
                    "price": self.data.close[0],
                    "rsi": rsi[0],
                    "atr": atr[0] if atr else None,
                    "reason": "rsi < 30",
                    "strategy_id": self.params.strategy_id,
                    "symbol": self.params.symbol,
                    "timeframe": self.params.timeframe
                })
        else:
            if rsi and rsi[0] > 70:
                self.sell()
                self.exit_log.append({
                    "timestamp": self.data.datetime.datetime(0),
                    "price": self.data.close[0],
                    "rsi": rsi[0],
                    "atr": atr[0] if atr else None,
                    "reason": "rsi > 70",
                    "strategy_id": self.params.strategy_id,
                    "symbol": self.params.symbol,
                    "timeframe": self.params.timeframe
                })
