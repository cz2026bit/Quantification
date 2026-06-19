"""参数寻优层：网格搜索。

对一个策略的可调参数，在其 [min, max] 区间内取若干候选值，把所有组合
逐一回测，汇总成一张表，方便找出「历史上表现最好」的参数。

⚠️ 教学提醒：网格搜索找到的"最优参数"是在历史数据上挑出来的，很可能是
**过拟合**——换一段时间或换只股票就失效。它用来理解"参数如何影响结果"，
而不是用来直接实盘。
"""

from __future__ import annotations

import itertools
from typing import Dict, List

import pandas as pd

from . import backtest
from .strategies import Strategy

# 控制组合爆炸：按参数个数决定每个参数取多少个候选值
_POINTS_BY_NDIM = {1: 25, 2: 15, 3: 8}


def candidate_values(param, n_points: int) -> List[int]:
    """在 [min, max] 上等间隔取 n_points 个整数候选值（含端点、去重）。"""
    lo, hi = param.min, param.max
    if hi <= lo:
        return [lo]
    step = max(1, round((hi - lo) / (n_points - 1)))
    vals = list(range(lo, hi + 1, step))
    if vals[-1] != hi:
        vals.append(hi)
    return sorted(set(vals))


def grid_search(
    df: pd.DataFrame,
    strategy: Strategy,
    fee: float = 0.0003,
    metric: str = "total_return",
) -> pd.DataFrame:
    """对 strategy 的全部参数做网格搜索。

    Args:
        df: 标准化行情。
        strategy: 待寻优策略（需有可调参数；隔夜策略无参数会报错）。
        fee: 单边手续费率。
        metric: 排序依据，可选 "total_return" / "sharpe" / "calmar"。

    Returns:
        DataFrame，每行一个参数组合，含各参数列与
        total_return / max_drawdown / sharpe / calmar / num_trades，
        已按 metric 降序排列。
    """
    if not strategy.params:
        raise ValueError(f"策略「{strategy.label}」没有可调参数，无法寻优。")

    n_points = _POINTS_BY_NDIM.get(len(strategy.params), 8)
    grids: Dict[str, List[int]] = {
        p.name: candidate_values(p, n_points) for p in strategy.params
    }
    names = list(grids.keys())

    rows = []
    for combo in itertools.product(*(grids[n] for n in names)):
        kwargs = dict(zip(names, combo))
        # 跳过"快线>=慢线"这类无意义组合（双均线/MACD）
        if "fast" in kwargs and "slow" in kwargs and kwargs["fast"] >= kwargs["slow"]:
            continue
        if "low" in kwargs and "high" in kwargs and kwargs["low"] >= kwargs["high"]:
            continue

        signal = strategy.func(df, **kwargs)
        if strategy.overnight:
            r = backtest.run_overnight_backtest(df, signal, fee=fee)
        else:
            r = backtest.run_backtest(df, signal, fee=fee)

        rows.append(
            {
                **kwargs,
                "total_return": r.total_return,
                "max_drawdown": r.max_drawdown,
                "sharpe": r.sharpe,
                "calmar": r.calmar,
                "num_trades": r.num_trades,
            }
        )

    result = pd.DataFrame(rows)
    if metric not in result.columns:
        metric = "total_return"
    return result.sort_values(metric, ascending=False).reset_index(drop=True)
