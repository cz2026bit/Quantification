"""回测引擎层。

核心思想（向量化回测，适合学习）：
    1. 策略在第 T 日收盘后给出信号 signal[T]；
    2. 第 T+1 日才按该信号持仓，吃到 T+1 日的收益 —— 所以 signal 要 shift(1)，
       这能避免"用当天收盘信号赚当天收益"的未来函数偏差；
    3. 在信号基础上叠加止损/止盈与仓位控制（风险管理）；
    4. 扣除换仓手续费后累乘得到净值曲线。

输出 BacktestResult 包含净值序列、逐笔交易、月度收益与一整组绩效指标，
其中 *最大回撤* 是本项目最关心的指标。
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
    position: pd.Series        # 实际持仓（已 shift 并叠加风控，0~1）
    trades: pd.DataFrame       # 逐笔交易明细
    monthly: pd.DataFrame      # 月度收益透视表（行=年，列=月）
    # ---- 绩效指标 ----
    total_return: float        # 累计收益率
    annual_return: float       # 年化收益率
    annual_volatility: float   # 年化波动率
    max_drawdown: float        # 最大回撤（负数）
    max_drawdown_days: int     # 最长回撤持续交易日数
    sharpe: float              # 夏普比率（无风险利率按 0）
    sortino: float             # 索提诺比率（只惩罚下行波动）
    calmar: float              # 卡玛比率 = 年化收益 / |最大回撤|
    win_rate: float            # 持仓日中上涨日占比
    num_trades: int            # 完整交易笔数（开仓→平仓算一笔）


def run_backtest(
    df: pd.DataFrame,
    signal: pd.Series,
    fee: float = 0.0003,
    stop_loss: float = 0.0,
    take_profit: float = 0.0,
    position_size: float = 1.0,
) -> BacktestResult:
    """对单只标的、单个信号序列做回测。

    Args:
        df: 标准化行情（需含 close 列）。
        signal: 持仓信号（0/1），索引与 df 对齐。
        fee: 单边换仓费率（含佣金+印花税的粗略估计），默认万三。
        stop_loss: 止损比例（如 0.1 表示自买入价回撤 10% 即平仓），0 表示关闭。
        take_profit: 止盈比例（如 0.2 表示自买入价上涨 20% 即平仓），0 表示关闭。
        position_size: 持仓时投入的资金比例（0~1），用于简单仓位管理。

    Returns:
        BacktestResult。
    """
    close = df["close"]
    daily_return = close.pct_change().fillna(0)

    # shift(1): 今天的持仓由昨天收盘的信号决定，杜绝未来函数
    base = signal.shift(1).fillna(0).clip(0, 1)

    # 叠加止损/止盈：根据持仓期间价格相对买入价的变化强制平仓
    held = _apply_stops(base, close, stop_loss, take_profit)

    # 仓位控制：持仓时只投入 position_size 比例的资金
    position = held * float(position_size)

    # 换仓发生在持仓变化的那一天，按变化幅度收取费用
    turnover = position.diff().abs().fillna(position.abs())
    cost = turnover * fee

    strategy_return = position * daily_return - cost
    equity = (1 + strategy_return).cumprod()
    benchmark = (1 + daily_return).cumprod()

    # 回撤 = 当前净值相对历史最高点的跌幅
    running_max = equity.cummax()
    drawdown = equity / running_max - 1

    trades = _extract_trades(close, held)

    result = BacktestResult(
        equity=equity,
        benchmark=benchmark,
        drawdown=drawdown,
        position=position,
        trades=trades,
        monthly=_monthly_returns(equity),
        total_return=float(equity.iloc[-1] - 1),
        annual_return=_annualized(equity),
        annual_volatility=float(strategy_return.std() * np.sqrt(TRADING_DAYS)),
        max_drawdown=float(drawdown.min()),
        max_drawdown_days=_max_drawdown_days(drawdown),
        sharpe=_sharpe(strategy_return),
        sortino=_sortino(strategy_return),
        calmar=_calmar(_annualized(equity), float(drawdown.min())),
        win_rate=_win_rate(daily_return, held),
        num_trades=len(trades),
    )
    return result


def _apply_stops(
    base: pd.Series,
    close: pd.Series,
    stop_loss: float,
    take_profit: float,
) -> pd.Series:
    """在信号基础上叠加止损/止盈，返回 0/1 的实际持仓。

    逐日推进：记录买入价，持仓期间若价格触发止损或止盈线则当日平仓；
    被止损/止盈打出后，需等信号重新归零再触发买入，才会再次入场
    （避免在同一波信号里被打出后立刻又买回）。
    """
    if stop_loss <= 0 and take_profit <= 0:
        return base  # 未开启风控，直接用原信号

    pos = pd.Series(0, index=base.index, dtype=int)
    in_pos = False
    entry = 0.0
    blocked = False  # 被风控打出后，在信号回到 0 之前禁止再入场

    for t in base.index:
        want = base.loc[t]
        price = close.loc[t]

        if not in_pos:
            if want == 0:
                blocked = False  # 信号归零，解除封锁
            if want == 1 and not blocked:
                in_pos = True
                entry = price
                pos.loc[t] = 1
        else:
            ret = price / entry - 1
            hit_stop = stop_loss > 0 and ret <= -stop_loss
            hit_take = take_profit > 0 and ret >= take_profit
            if hit_stop or hit_take:
                in_pos = False
                blocked = True   # 风控平仓，等信号归零再说
                pos.loc[t] = 0
            elif want == 0:
                in_pos = False   # 策略信号正常平仓
                pos.loc[t] = 0
            else:
                pos.loc[t] = 1   # 继续持有

    return pos


def _extract_trades(close: pd.Series, position: pd.Series) -> pd.DataFrame:
    """从 0/1 持仓序列还原逐笔交易明细。"""
    cols = ["买入日", "买入价", "卖出日", "卖出价", "收益率", "持有天数"]
    rows = []
    in_pos = False
    entry_date = entry_price = None

    for t in position.index:
        if position.loc[t] == 1 and not in_pos:
            in_pos = True
            entry_date, entry_price = t, close.loc[t]
        elif position.loc[t] == 0 and in_pos:
            in_pos = False
            rows.append(_make_trade(entry_date, entry_price, t, close.loc[t]))

    # 回测结束仍持仓：按最后一天收盘价平掉，计入未实现盈亏
    if in_pos:
        last = position.index[-1]
        rows.append(_make_trade(entry_date, entry_price, last, close.loc[last]))

    return pd.DataFrame(rows, columns=cols)


def _make_trade(d0, p0, d1, p1) -> dict:
    return {
        "买入日": d0.date(),
        "买入价": round(float(p0), 2),
        "卖出日": d1.date(),
        "卖出价": round(float(p1), 2),
        "收益率": round(float(p1 / p0 - 1), 4),
        "持有天数": int((d1 - d0).days),
    }


def _monthly_returns(equity: pd.Series) -> pd.DataFrame:
    """把净值转成「年×月」收益透视表，便于看哪些月份赚/亏。"""
    monthly = equity.resample("ME").last().pct_change().dropna()
    if monthly.empty:
        return pd.DataFrame()
    table = pd.DataFrame(
        {
            "year": monthly.index.year,
            "month": monthly.index.month,
            "ret": monthly.values,
        }
    )
    return table.pivot(index="year", columns="month", values="ret")


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


def _sortino(returns: pd.Series) -> float:
    downside = returns[returns < 0]
    dstd = downside.std()
    if dstd == 0 or np.isnan(dstd):
        return 0.0
    return float(returns.mean() / dstd * np.sqrt(TRADING_DAYS))


def _calmar(annual_return: float, max_drawdown: float) -> float:
    if max_drawdown == 0:
        return 0.0
    return float(annual_return / abs(max_drawdown))


def _max_drawdown_days(drawdown: pd.Series) -> int:
    """最长「水下」持续天数：净值未创新高的最长连续交易日数。"""
    underwater = drawdown < 0
    longest = current = 0
    for flag in underwater:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return int(longest)


def _win_rate(daily_return: pd.Series, position: pd.Series) -> float:
    held = daily_return[position > 0]
    if held.empty:
        return 0.0
    return float((held > 0).mean())
