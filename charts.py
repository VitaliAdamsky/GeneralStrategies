import pandas as pd
import matplotlib.pyplot as plt

# Загрузка данных
df = pd.read_csv("trades_full.csv")

# Удалим строки без прибыли
df = df.dropna(subset=["pnl_comm"])

# Кривая доходности — накопленная прибыль
df["equity"] = df["pnl_comm"].cumsum()

# Построение графика
plt.figure(figsize=(10, 4))
plt.plot(df["equity"], marker='o', color='blue')
plt.title("Кривая доходности (Equity Curve)")
plt.xlabel("Сделка")
plt.ylabel("Накопленная прибыль (USD)")
plt.grid(True)
plt.tight_layout()
plt.show()
