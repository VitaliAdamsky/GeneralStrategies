import plotly.graph_objects as go

def plot_strategy_chart(df, entry_log, exit_log, indicators, save_path):
    fig = go.Figure()

    # === Свечи ===
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Candles"
    ))

    # === Индикаторы ===
    for name, series in indicators.items():
        fig.add_trace(go.Scatter(
            x=df.index,
            y=series,
            mode="lines",
            name=name,
            line=dict(width=3)  # ← жирные линии
        ))

    # === Входы ===
    if entry_log:
        fig.add_trace(go.Scatter(
            x=[e["timestamp"] for e in entry_log],
            y=[e["price"] for e in entry_log],
            mode="markers",
            name="Buy",
            marker=dict(color="green", symbol="triangle-up", size=14)
        ))

    # === Выходы ===
    if exit_log:
        fig.add_trace(go.Scatter(
            x=[e["timestamp"] for e in exit_log],
            y=[e["price"] for e in exit_log],
            mode="markers",
            name="Sell",
            marker=dict(color="red", symbol="triangle-down", size=14)
        ))

    # === Оформление ===
    fig.update_layout(
        title="Strategy Execution Chart",
        xaxis_title="Date",
        yaxis_title="Price",
        template="plotly_white",  # ← белая тема
        xaxis_rangeslider_visible=False,
        height=700,
        font=dict(family="Arial", size=14),
        hovermode="x unified",
        plot_bgcolor="white",
        paper_bgcolor="white"
    )

    fig.write_html(str(save_path))
