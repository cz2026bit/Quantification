"""可视化层：把行情与 BacktestResult 画成 Plotly 图。

返回 plotly Figure，由 app.py 用 st.plotly_chart 渲染。
三张图：真实股价图（含买卖点）、净值对比图、回撤曲线图。
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .backtest import BacktestResult


def price_chart(
    df: pd.DataFrame,
    result: BacktestResult,
    show_signals: bool = True,
) -> go.Figure:
    """真实收盘价走势，可选叠加策略的买入/卖出时点。

    这是「真实股价」，单位是该股票的货币（美元/人民币）；区别于净值曲线。
    买点 = 持仓由 0 变 1 的日子；卖点 = 由 1 变 0 的日子。

    show_signals=False 时只画价格、不标买卖点——用于隔夜这类「每天都买卖」
    的策略，逐点标注会铺满全图、没有意义。
    """
    close = df["close"]

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=close.index, y=close.values, name="收盘价",
            line=dict(color="#2c3e50", width=1.5),
        )
    )

    title = "真实股价走势（含策略买卖点）"
    if show_signals:
        pos = result.position
        change = pos.diff().fillna(pos)
        buys = close[change > 0]   # 0 -> 1
        sells = close[change < 0]  # 1 -> 0
        fig.add_trace(
            go.Scatter(
                x=buys.index, y=buys.values, name="买入", mode="markers",
                marker=dict(symbol="triangle-up", size=10, color="#d62728"),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=sells.index, y=sells.values, name="卖出", mode="markers",
                marker=dict(symbol="triangle-down", size=10, color="#2ca02c"),
            )
        )
    else:
        title = "真实股价走势（隔夜策略每天买卖，不逐点标注）"

    fig.update_layout(
        title=title,
        xaxis_title="日期",
        yaxis_title="价格",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def equity_curve(result: BacktestResult) -> go.Figure:
    """策略净值 vs 买入持有基准。"""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=result.equity.index,
            y=result.equity.values,
            name="策略净值",
            line=dict(color="#d62728", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=result.benchmark.index,
            y=result.benchmark.values,
            name="买入持有",
            line=dict(color="#7f7f7f", width=1.5, dash="dash"),
        )
    )
    fig.update_layout(
        title="净值曲线（初始资金 = 1.0）",
        xaxis_title="日期",
        yaxis_title="净值",
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0),
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig


def drawdown_curve(result: BacktestResult) -> go.Figure:
    """回撤曲线：填充面积，直观看到最大回撤的深度与持续时间。"""
    dd_pct = result.drawdown * 100
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=dd_pct.index,
            y=dd_pct.values,
            name="回撤",
            fill="tozeroy",
            line=dict(color="#1f77b4", width=1),
        )
    )
    # 标注最大回撤点
    trough = dd_pct.idxmin()
    fig.add_annotation(
        x=trough,
        y=dd_pct.min(),
        text=f"最大回撤 {dd_pct.min():.1f}%",
        showarrow=True,
        arrowhead=2,
    )
    fig.update_layout(
        title="回撤曲线（%）",
        xaxis_title="日期",
        yaxis_title="回撤 %",
        hovermode="x unified",
        margin=dict(l=40, r=20, t=60, b=40),
    )
    return fig
