"""行情数据获取层。

统一对外暴露 ``load_history`` 一个函数，返回标准化的 DataFrame：
    索引: DatetimeIndex（升序）
    列:   open, high, low, close, volume （全部小写）

A股使用 akshare，美股使用 yfinance。两个数据源的字段名/格式差异
都在本模块内部抹平，下游（策略、回测）不需要关心数据来自哪个市场。
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

import pandas as pd

Market = Literal["A股", "美股"]

# 标准化后的列顺序，下游统一依赖这个约定
STANDARD_COLUMNS = ["open", "high", "low", "close", "volume"]


def load_history(
    symbol: str,
    market: Market,
    start: dt.date,
    end: dt.date,
) -> pd.DataFrame:
    """获取标准化的日线历史行情。

    Args:
        symbol: A股为6位代码（如 "600519"）；美股为 ticker（如 "AAPL"）。
        market: "A股" 或 "美股"。
        start, end: 起止日期（含端点）。

    Returns:
        标准化 DataFrame，见模块 docstring。

    Raises:
        ValueError: 代码无效或区间内无数据。
    """
    if market == "A股":
        df = _load_a_share(symbol, start, end)
    elif market == "美股":
        df = _load_us(symbol, start, end)
    else:  # pragma: no cover - 防御性分支
        raise ValueError(f"未知市场: {market}")

    if df.empty:
        raise ValueError(f"未获取到 {symbol} 在 {start}~{end} 的数据，请检查代码或日期。")

    df = df[STANDARD_COLUMNS].sort_index()
    df = df.dropna(subset=["close"])
    return df


def _load_a_share(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """A股：akshare 的前复权日线。"""
    import akshare as ak

    raw = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
        adjust="qfq",  # 前复权，回测更贴近真实收益
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    raw = raw.rename(
        columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close",
            "成交量": "volume",
        }
    )
    raw["date"] = pd.to_datetime(raw["date"])
    return raw.set_index("date")


def _load_us(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """美股：yfinance 的自动复权日线。"""
    import yfinance as yf

    raw = yf.download(
        symbol,
        start=start.strftime("%Y-%m-%d"),
        # yfinance 的 end 是开区间，+1 天保证含端点
        end=(end + dt.timedelta(days=1)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
    )
    if raw is None or raw.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    # 多 ticker 下载时列是 MultiIndex，这里只取单只，拍平成单层
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw = raw.rename(columns=str.lower)
    raw.index.name = "date"
    return raw
