"""可视化层：把 BacktestResult 画成 Plotly 图。

返回 plotly Figure，由 app.py 用 st.plotly_chart 渲染。
两张核心图：净值对比图、回撤曲线图。
"""

from __future__ import annotations

import plotly.graph_objects as go

from .backtest import BacktestResult


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
