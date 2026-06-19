"""交易策略层。

每个策略是一个函数：输入标准化行情 DataFrame，输出一列 *持仓信号*
（pandas Series，索引与行情对齐）：
    1  = 满仓持有
    0  = 空仓

策略只负责产生信号，不关心收益怎么算——那是 backtest 的事。
新增策略时：写一个返回信号 Series 的函数，再登记到 STRATEGIES 字典即可，
app.py 会自动把它显示在下拉框里。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict

import pandas as pd


@dataclass
class Param:
    """策略可调参数的描述，供界面自动生成输入框。"""

    name: str
    label: str
    default: int
    min: int
    max: int


@dataclass
class Strategy:
    """一个策略的完整定义：名称、说明、信号函数、可调参数。"""

    key: str
    label: str
    description: str
    func: Callable[..., pd.Series]
    params: list = field(default_factory=list)
    # 为 True 时走 backtest.run_overnight_backtest（尾盘买、次日开盘卖），
    # 而非普通的收盘到收盘回测。
    overnight: bool = False


def overnight_hold(df: pd.DataFrame) -> pd.Series:
    """隔夜持有：每天都参与（恒为 1）。

    真正的买卖时点由 backtest.run_overnight_backtest 处理——尾盘买入、
    次日开盘卖出。这里只声明"每晚都持有"。
    """
    return pd.Series(1, index=df.index, dtype=int)


def ma_cross(df: pd.DataFrame, fast: int = 5, slow: int = 20) -> pd.Series:
    """双均线交叉：快线上穿慢线则持有，下穿则空仓。"""
    fast_ma = df["close"].rolling(fast).mean()
    slow_ma = df["close"].rolling(slow).mean()
    signal = (fast_ma > slow_ma).astype(int)
    return signal


def rsi_reversal(df: pd.DataFrame, period: int = 14, low: int = 30, high: int = 70) -> pd.Series:
    """RSI 超买超卖：RSI 低于 low 时买入持有，高于 high 时卖出空仓。"""
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    rsi = 100 - 100 / (1 + rs)

    # 在 low/high 阈值间维持上一状态（迟滞），避免频繁进出
    signal = pd.Series(index=df.index, dtype="float64")
    signal[rsi < low] = 1
    signal[rsi > high] = 0
    signal = signal.ffill().fillna(0)
    return signal.astype(int)


def bollinger(df: pd.DataFrame, period: int = 20, num_std: int = 2) -> pd.Series:
    """布林带：价格跌破下轨买入，升破上轨卖出。"""
    mid = df["close"].rolling(period).mean()
    std = df["close"].rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std

    signal = pd.Series(index=df.index, dtype="float64")
    signal[df["close"] < lower] = 1
    signal[df["close"] > upper] = 0
    signal = signal.ffill().fillna(0)
    return signal.astype(int)


# 策略注册表：界面与回测都从这里读取
STRATEGIES: Dict[str, Strategy] = {
    "ma_cross": Strategy(
        key="ma_cross",
        label="双均线交叉",
        description="快线上穿慢线买入，下穿卖出。最经典的趋势跟踪入门策略。",
        func=ma_cross,
        params=[
            Param("fast", "快线周期", 5, 2, 60),
            Param("slow", "慢线周期", 20, 5, 250),
        ],
    ),
    "rsi_reversal": Strategy(
        key="rsi_reversal",
        label="RSI 超买超卖",
        description="RSI 跌破阈值买入、升破阈值卖出，属于均值回归思路。",
        func=rsi_reversal,
        params=[
            Param("period", "RSI 周期", 14, 2, 60),
            Param("low", "超卖阈值", 30, 5, 50),
            Param("high", "超买阈值", 70, 50, 95),
        ],
    ),
    "bollinger": Strategy(
        key="bollinger",
        label="布林带",
        description="价格触及下轨买入、触及上轨卖出，捕捉区间震荡。",
        func=bollinger,
        params=[
            Param("period", "中轨周期", 20, 5, 120),
            Param("num_std", "标准差倍数", 2, 1, 4),
        ],
    ),
    "overnight": Strategy(
        key="overnight",
        label="隔夜策略（尾盘买/开盘卖）",
        description=(
            "每天尾盘买入、次日开盘卖出，只赚『隔夜跳空』收益。"
            "注意：每天买卖一次，手续费很重，请重点观察扣费后还剩多少。"
        ),
        func=overnight_hold,
        params=[],
        overnight=True,
    ),
}
