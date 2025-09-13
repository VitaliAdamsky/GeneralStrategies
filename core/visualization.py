import plotly.graph_objects as go
from plotly.subplots import make_subplots

def plot_strategy_chart(df, entry_log, exit_log, indicators, save_path):
    num_indicators = len(indicators)
    total_rows = 1 + num_indicators  # 1 row for candles + N for indicators

    fig = make_subplots(
        rows=total_rows,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.6] + [0.4 / num_indicators] * num_indicators,
        subplot_titles=["Price"] + list(indicators.keys())
    )

    # === Свечи ===
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Candles"
    ), row=1, col=1)

    # === Входы ===
    if entry_log:
        fig.add_trace(go.Scatter(
            x=[e["timestamp"] for e in entry_log],
            y=[e["price"] for e in entry_log],
            mode="markers",
            name="Buy",
            marker=dict(color="green", symbol="triangle-up", size=14)
        ), row=1, col=1)

    # === Выходы ===
    if exit_log:
        fig.add_trace(go.Scatter(
            x=[e["timestamp"] for e in exit_log],
            y=[e["price"] for e in exit_log],
            mode="markers",
            name="Sell",
            marker=dict(color="red", symbol="triangle-down", size=14)
        ), row=1, col=1)

    # === Индикаторы ===
    for i, (name, series) in enumerate(indicators.items()):
        fig.add_trace(go.Scatter(
            x=df.index,
            y=series,
            mode="lines",
            name=name,
            line=dict(width=3)
        ), row=i + 2, col=1)

    # === Оформление ===
    fig.update_layout(
        title="Strategy Execution Chart",
        template="plotly_white",
        height=300 + 200 * total_rows,
        font=dict(family="Arial", size=14),
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
        plot_bgcolor="white",
        paper_bgcolor="white"
    )

    fig.write_html(str(save_path))
