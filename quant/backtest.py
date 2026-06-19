"""回测引擎层。

核心思想（向量化回测，适合学习）：
    1. 策略在第 T 日收盘后给出信号 signal[T]；
    2. 第 T+1 日才按该信号持仓，吃到 T+1 日的收益 —— 所以 signal 要 shift(1)，
       这能避免"用当天收盘信号赚当天收益"的未来函数偏差；
    3. 扣除换仓手续费后累乘得到净值曲线。

输出 BacktestResult 同时包含净值序列与一组常用绩效指标，其中
*最大回撤* 是本项目最关心的指标。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# A股/美股都按一年约 252 个交易日年化
TRADING_DAYS = 252


@dataclass
class BacktestResult:
    equity: pd.Series          # 策略净值曲线（初始 = 1.0）
    benchmark: pd.Series       # 买入持有基准净值（初始 = 1.0）
    drawdown: pd.Series        # 策略每日回撤（<=0）
    position: pd.Series        # 实际持仓（已 shift，0/1）
    total_return: float        # 累计收益率
    annual_return: float       # 年化收益率
    max_drawdown: float        # 最大回撤（负数）
    sharpe: float              # 夏普比率（无风险利率按 0）
    win_rate: float            # 持仓日中上涨日占比
    num_trades: int            # 换手次数（开/平仓各算一次）


def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    fee: float = 0.0003,
) -> BacktestResult:
    """对单只标的、单个信号序列做向量化回测。

    Args:
        df: 标准化行情（需含 close 列）。
        signal: 持仓信号（0/1），索引与 df 对齐。
        fee: 单边换仓费率（含佣金+印花税的粗略估计），默认万三。

    Returns:
        BacktestResult。
    """
    close = df["close"]
    daily_return = close.pct_change().fillna(0)

    # shift(1): 今天的持仓由昨天收盘的信号决定，杜绝未来函数
    position = signal.shift(1).fillna(0).clip(0, 1)

    # 换仓发生在持仓变化的那一天，按变化幅度收取费用
    turnover = position.diff().abs().fillna(position.abs())
    cost = turnover * fee

    strategy_return = position * daily_return - cost
    equity = (1 + strategy_return).cumprod()
    benchmark = (1 + daily_return).cumprod()

    # 回撤 = 当前净值相对历史最高点的跌幅
    running_max = equity.cummax()
    drawdown = equity / running_max - 1

    result = BacktestResult(
        equity=equity,
        benchmark=benchmark,
        drawdown=drawdown,
        position=position,
        total_return=float(equity.iloc[-1] - 1),
        annual_return=_annualized(equity),
        max_drawdown=float(drawdown.min()),
        sharpe=_sharpe(strategy_return),
        win_rate=_win_rate(daily_return, position),
        num_trades=int((turnover > 0).sum()),
    )
    return result


def _annualized(equity: pd.Series) -> float:
    n = len(equity)
    if n < 2 or equity.iloc[-1] <= 0:
        return 0.0
    return float(equity.iloc[-1] ** (TRADING_DAYS / n) - 1)


def _sharpe(returns: pd.Series) -> float:
    std = returns.std()
    if std == 0 or np.isnan(std):
        return 0.0
    return float(returns.mean() / std * np.sqrt(TRADING_DAYS))


def _win_rate(daily_return: pd.Series, position: pd.Series) -> float:
    held = daily_return[position > 0]
    if held.empty:
        return 0.0
    return float((held > 0).mean())
